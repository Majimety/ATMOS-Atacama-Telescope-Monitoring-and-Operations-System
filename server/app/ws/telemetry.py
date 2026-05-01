"""
telemetry.py — WebSocket broadcast layer for ATMOS
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
from app.obs_queue import scheduler
from influx_writer import influx_writer

logger = logging.getLogger(__name__)

_TICK_INTERVAL: float = 1.0


class ConnectionPool:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("Client connected — pool size: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("Client disconnected — pool size: %d", len(self._connections))

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, payload: dict) -> None:
        if not self._connections:
            return

        message = json.dumps(payload, default=str)
        snapshot = list(self._connections)

        results = await asyncio.gather(
            *[ws.send_text(message) for ws in snapshot],
            return_exceptions=True,
        )

        dead = {
            ws for ws, result in zip(snapshot, results) if isinstance(result, Exception)
        }
        if dead:
            self._connections -= dead
            logger.warning("Pruned %d dead connection(s) from pool", len(dead))


pool = ConnectionPool()

_broadcast_task: asyncio.Task | None = None


async def _broadcast_loop() -> None:
    logger.info("Broadcast loop started (interval=%.1fs)", _TICK_INTERVAL)
    while True:
        tick_start = asyncio.get_event_loop().time()
        try:
            await _tick()
        except Exception:
            logger.exception("Unhandled exception in broadcast loop tick")

        elapsed = asyncio.get_event_loop().time() - tick_start
        await asyncio.sleep(max(0.0, _TICK_INTERVAL - elapsed))


async def _tick() -> None:
    snapshot = await get_system_snapshot()

    await scheduler.tick(snapshot)
    snapshot["scheduler"] = scheduler.get_state()

    asyncio.create_task(influx_writer.write(snapshot))

    await pool.broadcast(snapshot)


def _ensure_broadcast_loop() -> None:
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_loop())


async def telemetry_endpoint(ws: WebSocket) -> None:
    """
    Handle a single WebSocket client connection.
    Authentication is performed by the caller (main.py ws_telemetry) before
    this function is invoked — do NOT call ws_authenticate again here.
    """
    _ensure_broadcast_loop()
    await pool.connect(ws)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                _handle_command(json.loads(raw))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Malformed command payload: %s", exc)

    except WebSocketDisconnect:
        pool.disconnect(ws)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        pool.disconnect(ws)


def _handle_command(command: dict) -> None:
    cmd_type = command.get("type")

    if cmd_type == "slew":
        az = float(command.get("az", 183.7))
        el = float(command.get("el", 52.4))
        name = command.get("target_name", "Custom")
        cmd_slew(az, el, name)
        logger.info("SLEW → Az:%.2f° El:%.2f° (%s)", az, el, name)

    elif cmd_type == "stow":
        cmd_stow()
        logger.info("STOW ALL")

    elif cmd_type == "set_band":
        band = int(command.get("band", 6))
        cmd_set_band(band)
        logger.info("BAND → B%d", band)

    elif cmd_type == "set_mode":
        mode = command.get("mode", "interferometry")
        cmd_set_mode(mode)
        logger.info("MODE → %s", mode)

    elif cmd_type == "inject_fault":
        dish_id = command.get("dishId", "")
        offline = command.get("offline", True)
        if dish_id:
            cmd_inject_fault(dish_id, offline)
            logger.warning(
                "FAULT %s → %s",
                "INJECTED" if offline else "CLEARED",
                dish_id,
            )

    elif cmd_type == "clear_fault":
        dish_id = command.get("dishId", "")
        if dish_id:
            cmd_clear_fault(dish_id)
            logger.info("FAULT CLEARED → %s", dish_id)

    elif cmd_type == "emergency_stop":
        cmd_stow()
        logger.critical("EMERGENCY STOP — all dishes commanded to stow")

    else:
        logger.warning("Unknown command type: %r", cmd_type)
