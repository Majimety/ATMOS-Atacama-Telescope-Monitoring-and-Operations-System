"""
telemetry.py — WebSocket broadcast layer for ATMOS
====================================================

Architecture
------------
A single background task (``_broadcast_loop``) owns the tick pipeline:

    1. Build system snapshot (async; fetches live weather when available).
    2. Advance the observation scheduler against live atmospheric constraints.
    3. Fire-and-forget InfluxDB write (batched, never blocks the loop).
    4. Broadcast the complete snapshot to *all* connected clients via
       ``ConnectionPool.broadcast()``.
    5. Sleep for the remainder of the 1-second cadence.

Each ``telemetry_endpoint`` coroutine (one per WebSocket connection) only:

    - Registers the socket with the pool on connect.
    - Listens for inbound control commands and dispatches them.
    - Removes the socket from the pool on disconnect or error.

This separation ensures that every connected client receives every frame,
regardless of which connection happened to trigger the snapshot build.
Previously the snapshot was sent only to the originating connection
(``ws.send_text`` inside the per-connection loop), so clients beyond the
first would never receive any telemetry.
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
from app.scheduler import scheduler
from influx_writer import influx_writer

logger = logging.getLogger(__name__)

# Interval between telemetry frames (seconds).
_TICK_INTERVAL: float = 1.0


# ── Connection pool ───────────────────────────────────────────────────────────


class ConnectionPool:
    """
    Registry of active WebSocket connections with concurrent fan-out delivery.

    ``broadcast`` serialises a payload to JSON once and delivers it to all
    registered sockets concurrently via ``asyncio.gather``.  Any socket that
    raises during the send is considered dead and pruned from the registry
    automatically, so a single broken client cannot stall delivery to others.
    """

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
        """
        Deliver *payload* to all registered sockets.

        The payload is serialised to JSON exactly once.  Delivery to all
        sockets is concurrent (single ``gather`` call).  Sockets that raise
        any exception are collected post-gather and evicted from the pool;
        they are never retried within the same frame.
        """
        if not self._connections:
            return

        message = json.dumps(payload, default=str)
        snapshot = list(self._connections)  # stable copy for zip below

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


# ── Background broadcast loop ─────────────────────────────────────────────────

_broadcast_task: asyncio.Task | None = None


async def _broadcast_loop() -> None:
    """
    Singleton tick loop that drives the entire telemetry pipeline.

    Started on the first WebSocket connection and kept alive until the event
    loop is shut down (or the task is explicitly cancelled).  The loop
    continues even when the pool is empty so that the scheduler and InfluxDB
    writer remain active during brief disconnection windows — observations in
    progress are not interrupted by a client refresh.
    """
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
    """
    Execute one telemetry frame.

    Steps:

    1. Obtain the current system snapshot from the simulation layer.
    2. Advance the observation scheduler with the latest atmospheric data
       so constraint evaluation (elevation, PWV, wind) uses fresh values.
    3. Enqueue an InfluxDB write via ``ensure_future``; a slow or
       unavailable InfluxDB instance cannot delay frame delivery because
       the write runs concurrently in the event loop rather than serially.
    4. Broadcast the annotated snapshot to all connected WebSocket clients.
    """
    snapshot = await get_system_snapshot()

    await scheduler.tick(snapshot)
    snapshot["scheduler"] = scheduler.get_state()

    asyncio.ensure_future(influx_writer.write(snapshot))

    await pool.broadcast(snapshot)


def _ensure_broadcast_loop() -> None:
    """
    Start the singleton broadcast loop if it is not already running.

    Uses a module-level task handle so that re-entrant calls from subsequent
    connections are no-ops.  A done task (cancelled or errored) is restarted
    automatically to guard against unexpected task death.
    """
    global _broadcast_task
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.ensure_future(_broadcast_loop())


# ── Per-connection endpoint ───────────────────────────────────────────────────


async def telemetry_endpoint(ws: WebSocket) -> None:
    """
    Handle a single WebSocket client connection.

    Registers the socket with the pool (so the broadcast loop includes it in
    subsequent frames), then enters a receive loop that dispatches inbound
    control commands.  This coroutine does *not* drive the tick cycle; that
    responsibility belongs exclusively to ``_broadcast_loop``.

    On disconnect or any WebSocket-level error the socket is removed from the
    pool and the coroutine returns cleanly — no exception propagates to the
    ASGI layer.
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


# ── Command dispatcher ────────────────────────────────────────────────────────


def _handle_command(command: dict) -> None:
    """
    Dispatch a validated inbound control command to the simulation layer.

    All commands are synchronous and fire-and-forget; updated state is
    reflected in the next broadcast frame without any explicit acknowledgement
    message.
    """
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
