import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")  # empty = disabled
INFLUX_ORG = os.getenv("INFLUX_ORG", "atmos")
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
        self._ClientClass = None
        self._enabled = bool(INFLUX_TOKEN)
        self._pending: dict[str, list] = {"telemetry": [], "atmosphere": []}
        self._last_flush = time.time()
        self._batch_size = 50  # flush after this many total points
        self._flush_interval = 10  # flush every N seconds regardless
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

    def _build_points(self, snapshot: dict) -> dict[str, list]:
        """
        Convert snapshot → InfluxDB Point objects grouped by target bucket.
        Returns {"telemetry": [...], "atmosphere": [...]}
        """
        try:
            from influxdb_client import Point, WritePrecision
        except ImportError:
            return {"telemetry": [], "atmosphere": []}

        ts_ns = int(time.time_ns())
        tel_points = []
        atm_points = []

        # ── Per-dish telemetry ────────────────────────────────────────────
        alma = snapshot.get("alma", {})
        for dish in alma.get("dishes", []):
            if not dish.get("online"):
                continue
            p = (
                Point("dish_telemetry")
                .tag("dish_id", dish.get("id", "unknown"))
                .tag("ant_type", dish.get("ant_type", "DA"))
                .tag("band", str(snapshot.get("system", {}).get("band", 6)))
                .field("tsys_k", float(dish.get("tsys_k") or 0))
                .field("signal_dbm", float(dish.get("signal_dbm") or -999))
                .field("az_deg", float(dish.get("az_deg") or 0))
                .field("el_deg", float(dish.get("el_deg") or 0))
                .field("online", True)
                .time(ts_ns, WritePrecision.NANOSECONDS)
            )
            tel_points.append(p)

        # ── Array-level summary ───────────────────────────────────────────
        tel_points.append(
            Point("array_summary")
            .tag(
                "obs_mode", snapshot.get("system", {}).get("obs_mode", "interferometry")
            )
            .field("online_count", int(alma.get("online_count", 0)))
            .field("avg_tsys_k", float(alma.get("avg_tsys_k") or 0))
            .time(ts_ns, WritePrecision.NANOSECONDS)
        )

        # ── Atmosphere → แยก bucket ───────────────────────────────────────
        atm = snapshot.get("atmosphere", {})
        if atm:
            atm_points.append(
                Point("atmosphere")
                .tag("source", atm.get("source", "simulation"))
                .field("pwv_mm", float(atm.get("pwv_mm", 0)))
                .field("tau_225ghz", float(atm.get("tau_225ghz", 0)))
                .field("wind_ms", float(atm.get("wind_ms", 0)))
                .field("wind_dir_deg", float(atm.get("wind_dir_deg", 0)))
                .field("temp_c", float(atm.get("temp_c", 0)))
                .field("humidity_pct", float(atm.get("humidity_pct", 0)))
                .field("pressure_hpa", float(atm.get("pressure_hpa", 0)))
                .time(ts_ns, WritePrecision.NANOSECONDS)
            )

        return {"telemetry": tel_points, "atmosphere": atm_points}

    async def write(self, snapshot: dict):
        """
        Non-blocking write — adds points to pending buffer per bucket.
        Flushes when buffer is full or interval has elapsed.
        Safe to await every second; will never raise.
        """
        if not self._enabled:
            return

        self._ensure_client()
        if not self._enabled:  # may have been disabled by _ensure_client
            return

        self._frame_count += 1
        grouped = self._build_points(snapshot)
        self._pending["telemetry"].extend(grouped["telemetry"])
        self._pending["atmosphere"].extend(grouped["atmosphere"])

        now = time.time()
        total_pending = sum(len(v) for v in self._pending.values())
        should_flush = (
            total_pending >= self._batch_size
            or (now - self._last_flush) >= self._flush_interval
        )

        if should_flush and total_pending:
            await self._flush()

    async def _flush(self):
        """
        Write each bucket's pending points using a single persistent client.
        เปิด client ครั้งเดียว flush ทั้ง 2 buckets แล้วปิด — ไม่เปิดใหม่ทุก flush
        """
        total = sum(len(v) for v in self._pending.values())
        if total == 0:
            return

        # Snapshot and clear pending atomically
        to_write = {k: v[:] for k, v in self._pending.items()}
        for v in self._pending.values():
            v.clear()
        self._last_flush = time.time()

        bucket_map = {
            "telemetry": INFLUX_BUCKET,
            "atmosphere": INFLUX_ATM_BUCKET,
        }

        try:
            async with self._ClientClass(
                url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
            ) as client:
                write_api = client.write_api()
                for key, points in to_write.items():
                    if not points:
                        continue
                    await write_api.write(bucket=bucket_map[key], record=points)
                    logger.debug(
                        f"InfluxDB: wrote {len(points)} points → {bucket_map[key]}"
                    )
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            if self._error_count % 60 == 1:
                logger.warning(f"InfluxDB write failed ({self._error_count}x): {exc}")

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "url": INFLUX_URL if self._enabled else None,
            "org": INFLUX_ORG if self._enabled else None,
            "buckets": (
                {
                    "telemetry": INFLUX_BUCKET,
                    "atmosphere": INFLUX_ATM_BUCKET,
                }
                if self._enabled
                else None
            ),
            "frames_seen": self._frame_count,
            "pending": {k: len(v) for k, v in self._pending.items()},
            "error_count": self._error_count,
            "last_error": self._last_error,
        }


# ── Singleton used by telemetry loop ──────────────────────────────────────────
influx_writer = InfluxWriter()
