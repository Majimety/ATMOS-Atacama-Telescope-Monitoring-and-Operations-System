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
from app.scheduler import scheduler
from influx_writer import influx_writer

logger = logging.getLogger(__name__)


# ── Connection pool ────────────────────────────────────────────────────────────


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

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, payload: dict):
        if not self._connections:
            return

        message = json.dumps(payload, default=str)
        results = await asyncio.gather(
            *[ws.send_text(message) for ws in list(self._connections)],
            return_exceptions=True,
        )

        dead = {
            ws
            for ws, result in zip(list(self._connections), results)
            if isinstance(result, Exception)
        }
        self._connections -= dead


pool = ConnectionPool()


# ── Global broadcast loop (singleton — started once at server startup) ─────────

_broadcast_task: asyncio.Task | None = None


async def _broadcast_loop():
    """
    ทำงาน 1 Hz ตลอดอายุ server — ไม่ขึ้นกับจำนวน client ที่เชื่อมต่ออยู่

    Pipeline ต่อ tick:
      1. Build snapshot
      2. Advance scheduler (ครั้งเดียวต่อวินาที)
      3. Write to InfluxDB (non-blocking)
      4. Broadcast ไปทุก client พร้อมกัน
    """
    logger.info("Broadcast loop started")
    while True:
        try:
            tick_start = asyncio.get_event_loop().time()

            # 1. Build telemetry snapshot
            snapshot = await get_system_snapshot()

            # 2. Advance scheduler — เรียกครั้งเดียวต่อ tick ไม่ว่าจะมีกี่ client
            await scheduler.tick(snapshot)
            snapshot["scheduler"] = scheduler.get_state()

            # 3. Write to InfluxDB (fire-and-forget, errors swallowed inside writer)
            asyncio.ensure_future(influx_writer.write(snapshot))

            # 4. Broadcast ไปทุก client พร้อมกัน
            await pool.broadcast(snapshot)

            # รักษา 1 Hz โดยหักเวลาที่ใช้ไปแล้วใน tick
            elapsed = asyncio.get_event_loop().time() - tick_start
            await asyncio.sleep(max(0.0, 1.0 - elapsed))

        except asyncio.CancelledError:
            logger.info("Broadcast loop cancelled")
            break
        except Exception as exc:
            logger.error(f"Broadcast loop error: {exc}")
            await asyncio.sleep(1.0)  # ป้องกัน tight loop ถ้า snapshot crash


def ensure_broadcast_loop():
    """เรียกครั้งแรกที่มี client connect — สร้าง background task ถ้ายังไม่มี"""
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.ensure_future(_broadcast_loop())
        logger.info("Broadcast task created")


# ── Per-connection endpoint ────────────────────────────────────────────────────


async def telemetry_endpoint(ws: WebSocket):
    """
    WebSocket endpoint — ws://localhost:8000/ws/telemetry

    รับ client เข้า pool แล้วรอ command เท่านั้น
    Data จะไหลมาจาก _broadcast_loop() ผ่าน pool.broadcast()
    """
    await pool.connect(ws)
    ensure_broadcast_loop()  # ตรวจว่า broadcast loop ทำงานอยู่

    try:
        # รอ command จาก client ตลอดเวลา (ไม่มี timeout — block ได้เลย)
        while True:
            try:
                raw = await ws.receive_text()
                _handle_command(json.loads(raw))
            except json.JSONDecodeError:
                pass  # malformed command — ข้ามไป

    except WebSocketDisconnect:
        pool.disconnect(ws)
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        pool.disconnect(ws)


def _handle_command(command: dict):
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

    elif cmd_type == "emergency_stop":
        cmd_stow()
        logger.critical("EMERGENCY STOP — all dishes stowing")

    else:
        logger.warning(f"Unknown command: {cmd_type}")
