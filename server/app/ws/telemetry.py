"""
telemetry.py — WebSocket handler สำหรับ ATMOS

รับ connection จาก Frontend แล้ว stream snapshot ทุก 1 วินาที
รับ command จาก Frontend (slew, stow, set_band, set_mode, inject_fault)
"""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.simulation.alma_sim import (
    get_system_snapshot,
    cmd_slew,
    cmd_stow,
    cmd_set_band,
    cmd_set_mode,
    cmd_inject_fault,
    cmd_clear_fault,
)


logger = logging.getLogger(__name__)


class ConnectionPool:
    """จัดการ WebSocket connections หลายอันพร้อมกัน"""

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.info(f"Client connected — total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        logger.info(f"Client disconnected — total: {len(self._connections)}")

    async def broadcast(self, payload: dict):
        if not self._connections:
            return

        message = json.dumps(payload, default=str)
        results = await asyncio.gather(
            *[ws.send_text(message) for ws in self._connections],
            return_exceptions=True,
        )

        dead = {
            ws
            for ws, result in zip(self._connections, results)
            if isinstance(result, Exception)
        }
        self._connections -= dead


pool = ConnectionPool()


async def telemetry_endpoint(ws: WebSocket):
    """
    WebSocket endpoint — ws://localhost:8000/ws/telemetry

    Loop:
      1. build snapshot (async — ดึง weather จริงถ้ามี)
      2. ส่งไป client
      3. รอรับ command สูงสุด 1 วินาที (non-blocking)
      4. ถ้ามี command → process แล้วกลับขึ้น 1
    """
    await pool.connect(ws)

    try:
        while True:
            # get_system_snapshot เป็น async ตอนนี้
            snapshot = await get_system_snapshot()
            await ws.send_text(json.dumps(snapshot, default=str))

            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
                _handle_command(json.loads(raw))
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pool.disconnect(ws)
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        pool.disconnect(ws)


def _handle_command(command: dict):
    """
    Process command จาก Frontend
    ใช้ cmd_* functions จาก alma_sim ซึ่งแก้ global state
    """
    cmd_type = command.get("type")

    if cmd_type == "slew":
        az = float(command.get("az", 183.7))
        el = float(command.get("el", 52.4))
        name = command.get("target_name", "Custom")
        cmd_slew(az, el, name)
        logger.info(f"SLEW → Az:{az}° El:{el}° ({name})")

    elif cmd_type == "stow":
        cmd_stow()
        logger.info("STOW ALL")

    elif cmd_type == "set_band":
        band = int(command.get("band", 6))
        cmd_set_band(band)
        logger.info(f"BAND → {band}")

    elif cmd_type == "set_mode":
        mode = command.get("mode", "interferometry")
        cmd_set_mode(mode)
        logger.info(f"MODE → {mode}")

    elif cmd_type == "inject_fault":
        dish_id = command.get("dishId", "")
        offline = command.get("offline", True)
        if dish_id:
            cmd_inject_fault(dish_id, offline)
            logger.warning(f"FAULT {'INJECTED' if offline else 'CLEARED'} → {dish_id}")

    elif cmd_type == "clear_fault":
        dish_id = command.get("dishId", "")
        if dish_id:
            cmd_clear_fault(dish_id)
            logger.info(f"FAULT CLEARED → {dish_id}")

    elif cmd_type == "emergency_stop":
        cmd_stow()
        logger.critical("EMERGENCY STOP — all dishes stowing")

    else:
        logger.warning(f"Unknown command: {cmd_type}")
