"""
influx_writer.py — ATMOS InfluxDB Time-Series Writer
=====================================================

Writes every telemetry snapshot to InfluxDB using a persistent async
client with batching. Designed to be called from the WebSocket broadcast
loop once per second.

Usage (in telemetry.py or alma_sim.py):
    from influx_writer import influx_writer
    await influx_writer.write(snapshot)

Environment variables:
    INFLUX_URL    — default http://localhost:8086
    INFLUX_TOKEN  — required for production (leave empty to disable writes)
    INFLUX_ORG    — default "atmos"
    INFLUX_BUCKET — default "atmos_telemetry"
"""

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "")          # empty = disabled
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "atmos")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "atmos_telemetry")
INFLUX_ATM_BUCKET = os.getenv("INFLUX_ATM_BUCKET", "atmos_atmosphere")


class InfluxWriter:
    """
    Persistent async InfluxDB writer with:
    - Lazy client initialization (won't fail at import if InfluxDB is absent)
    - Write batching: flushes every N frames or every T seconds
    - Graceful disable when INFLUX_TOKEN is not set
    - Error suppression: InfluxDB being down never crashes the telemetry loop
    """

    def __init__(self):
        self._client = None
        self._write_api = None
        self._enabled = bool(INFLUX_TOKEN)
        self._pending: list = []
        self._last_flush = time.time()
        self._batch_size = 50       # flush after this many points
        self._flush_interval = 10   # flush every N seconds regardless
        self._frame_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        if self._enabled:
            logger.info(f"InfluxDB writer enabled — {INFLUX_URL} / {INFLUX_ORG}")
        else:
            logger.info("InfluxDB writer disabled (INFLUX_TOKEN not set)")

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
            # Store class ref — instantiate per-write to avoid event loop issues
            self._ClientClass = InfluxDBClientAsync
            logger.info("InfluxDB client class loaded")
        except ImportError:
            logger.warning("influxdb-client not installed — InfluxDB writes disabled")
            self._enabled = False

    def _build_points(self, snapshot: dict) -> list:
        """Convert a snapshot dict into InfluxDB Point objects."""
        try:
            from influxdb_client import Point, WritePrecision
        except ImportError:
            return []

        points = []
        ts_ns = int(time.time_ns())

        # ── Per-dish telemetry ────────────────────────────────────────────
        alma = snapshot.get("alma", {})
        for dish in alma.get("dishes", []):
            if not dish.get("online"):
                continue
            p = (
                Point("dish_telemetry")
                .tag("dish_id",  dish.get("id", "unknown"))
                .tag("ant_type", dish.get("ant_type", "DA"))
                .tag("band",     str(snapshot.get("system", {}).get("band", 6)))
                .field("tsys_k",     float(dish.get("tsys_k")   or 0))
                .field("signal_dbm", float(dish.get("signal_dbm") or -999))
                .field("az_deg",     float(dish.get("az_deg")   or 0))
                .field("el_deg",     float(dish.get("el_deg")   or 0))
                .field("online",     True)
                .time(ts_ns, WritePrecision.NANOSECONDS)
            )
            points.append(p)

        # ── Array-level summary ───────────────────────────────────────────
        points.append(
            Point("array_summary")
            .tag("obs_mode", snapshot.get("system", {}).get("obs_mode", "interferometry"))
            .field("online_count", int(alma.get("online_count", 0)))
            .field("avg_tsys_k",   float(alma.get("avg_tsys_k") or 0))
            .time(ts_ns, WritePrecision.NANOSECONDS)
        )

        # ── Atmosphere ────────────────────────────────────────────────────
        atm = snapshot.get("atmosphere", {})
        if atm:
            points.append(
                Point("atmosphere")
                .tag("source", atm.get("source", "simulation"))
                .field("pwv_mm",       float(atm.get("pwv_mm",       0)))
                .field("tau_225ghz",   float(atm.get("tau_225ghz",   0)))
                .field("wind_ms",      float(atm.get("wind_ms",      0)))
                .field("wind_dir_deg", float(atm.get("wind_dir_deg", 0)))
                .field("temp_c",       float(atm.get("temp_c",       0)))
                .field("humidity_pct", float(atm.get("humidity_pct", 0)))
                .field("pressure_hpa", float(atm.get("pressure_hpa", 0)))
                .time(ts_ns, WritePrecision.NANOSECONDS)
            )

        return points

    async def write(self, snapshot: dict):
        """
        Non-blocking write — adds points to pending buffer.
        Flushes when buffer is full or interval has elapsed.
        Safe to await every second; will never raise.
        """
        if not self._enabled:
            return

        self._ensure_client()
        if not self._enabled:   # may have been disabled by _ensure_client
            return

        self._frame_count += 1
        points = self._build_points(snapshot)
        self._pending.extend(points)

        now = time.time()
        should_flush = (
            len(self._pending) >= self._batch_size
            or (now - self._last_flush) >= self._flush_interval
        )

        if should_flush and self._pending:
            await self._flush()

    async def _flush(self):
        if not self._pending:
            return

        points_to_write = self._pending[:]
        self._pending.clear()
        self._last_flush = time.time()

        try:
            async with self._ClientClass(
                url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
            ) as client:
                write_api = client.write_api()
                await write_api.write(bucket=INFLUX_BUCKET, record=points_to_write)
                logger.debug(f"InfluxDB: wrote {len(points_to_write)} points")
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            # Don't log every second if InfluxDB is just down
            if self._error_count % 60 == 1:
                logger.warning(f"InfluxDB write failed ({self._error_count}x): {exc}")

    def status(self) -> dict:
        return {
            "enabled":      self._enabled,
            "url":          INFLUX_URL if self._enabled else None,
            "org":          INFLUX_ORG if self._enabled else None,
            "bucket":       INFLUX_BUCKET if self._enabled else None,
            "frames_seen":  self._frame_count,
            "pending":      len(self._pending),
            "error_count":  self._error_count,
            "last_error":   self._last_error,
        }


# ── Singleton used by telemetry loop ──────────────────────────────────────────
influx_writer = InfluxWriter()
