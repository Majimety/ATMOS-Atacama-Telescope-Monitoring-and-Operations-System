import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.simulation.alma_sim import (
    get_system_snapshot,
    set_band,
    set_obs_mode,
    inject_fault,
)
from app.simulation.pointing_sim import controller


logger = logging.getLogger(__name__)


class ConnectionPool:
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
        message = json.dumps(payload)
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


async def telemetry_endpoint(ws: WebSocket):
    await pool.connect(ws)
    try:
        while True:
            az, el, mode = controller.step()
            snapshot = get_system_snapshot(az_commanded=az, el_commanded=el)
            snapshot["pointing_mode"] = mode

            await ws.send_text(json.dumps(snapshot))

            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
                command = json.loads(raw)
                _handle_command(command)
            except asyncio.TimeoutError:
                pass  # ไม่มี command จาก client รอบนี้ — ปกติ
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from client — ignored")

    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        # จับ network drop, client crash และ error อื่นๆ ที่ไม่คาดคิด
        logger.warning(f"WebSocket error: {e}")
    finally:
        # finally การันตีว่า disconnect ถูกเรียกเสมอ ไม่ว่า error แบบไหน
        pool.disconnect(ws)


def _handle_command(command: dict):
    cmd = command.get("type")

    if cmd == "slew":
        az = float(command.get("az", 183.7))
        el = float(command.get("el", 52.4))
        controller.command_slew(az, el)
        logger.info(f"Slew → Az:{az} El:{el}")

    elif cmd == "stow":
        controller.command_stow()
        logger.info("STOW ALL")

    elif cmd == "set_band":
        band = int(command.get("band", 6))
        set_band(band)
        logger.info(f"Band → {band}")

    elif cmd == "set_mode":
        mode = command.get("mode", "interferometry")
        set_obs_mode(mode)
        logger.info(f"Mode → {mode}")

    elif cmd == "inject_fault":
        dish_id = command.get("dish_id", "")
        offline = bool(command.get("offline", True))
        inject_fault(dish_id, offline)
        logger.info(f"Fault inject: {dish_id} offline={offline}")

    else:
        logger.warning(f"Unknown command type: {cmd!r}")
