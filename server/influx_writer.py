"""
influx_writer.py — Persistent async InfluxDB writer for ATMOS
==============================================================

Design goals
------------
1. **Lazy initialisation** — the client is not created at import time; it is
   instantiated on the first call to ``write()``.  This means a missing or
   unreachable InfluxDB instance does not prevent the application from
   starting.

2. **Persistent connection** — a single ``InfluxDBClientAsync`` instance is
   kept alive for the lifetime of the application and reused across all flush
   cycles.  The previous implementation opened and closed a new HTTP
   connection on every flush (every 10 seconds), which incurred unnecessary
   TLS and TCP handshake overhead.  The persistent client maintains a
   connection pool internally and reconnects transparently on transient
   failures.

3. **Write batching** — telemetry points are accumulated in an in-memory
   buffer and flushed either when the buffer reaches ``_BATCH_SIZE`` total
   points or when ``_FLUSH_INTERVAL`` seconds have elapsed, whichever comes
   first.  This amortises the per-request HTTP overhead across multiple
   frames while bounding maximum write latency.

4. **Graceful degradation** — when ``INFLUX_TOKEN`` is not set or the
   ``influxdb-client`` package is not installed, the writer disables itself
   silently.  Write errors are counted and logged but never propagated; a
   malfunctioning InfluxDB instance cannot crash the telemetry loop.

5. **Clean shutdown** — ``close()`` flushes any remaining buffered points and
   closes the underlying HTTP client.  It should be called from an ASGI
   lifespan shutdown hook to avoid data loss on graceful restart.

Environment variables
---------------------
INFLUX_URL            Base URL of the InfluxDB v2 instance.
                      Default: http://localhost:8086
INFLUX_TOKEN          All-access or write-scoped API token.
                      If empty, the writer is disabled entirely.
INFLUX_ORG            Organisation name.  Default: atmos
INFLUX_BUCKET         Primary bucket for per-dish telemetry and array
                      summary data.  Default: atmos_telemetry
INFLUX_ATM_BUCKET     Secondary bucket for atmospheric measurements.
                      Default: atmos_atmosphere
"""

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "atmos")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "atmos_telemetry")
INFLUX_ATM_BUCKET = os.getenv("INFLUX_ATM_BUCKET", "atmos_atmosphere")

# Flush when either threshold is crossed.
_BATCH_SIZE = 50  # total accumulated points
_FLUSH_INTERVAL = 10  # seconds


class InfluxWriter:
    """
    Stateful async writer that buffers telemetry snapshots and flushes them
    to InfluxDB v2 in batches.

    Thread-safety note: this class is designed for use within a single asyncio
    event loop.  The buffer mutations in ``write()`` and ``_flush()`` are not
    protected by a lock because both coroutines run on the same loop and
    asyncio is cooperative — no two coroutines modify the buffer concurrently.
    """

    def __init__(self) -> None:
        self._client = None  # InfluxDBClientAsync, created lazily
        self._write_api = None  # client.write_api(), retained across flushes
        self._ClientClass = None  # class reference, loaded once at first use
        self._enabled = bool(INFLUX_TOKEN)
        self._pending: dict[str, list] = {"telemetry": [], "atmosphere": []}
        self._last_flush = time.time()
        self._frame_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

        if self._enabled:
            logger.info(
                "InfluxDB writer enabled — url=%s org=%s", INFLUX_URL, INFLUX_ORG
            )
        else:
            logger.info("InfluxDB writer disabled (INFLUX_TOKEN not set)")

    # ── Initialisation ────────────────────────────────────────────────────────

    async def _ensure_client(self) -> bool:
        """
        Lazily create the persistent ``InfluxDBClientAsync`` and its write API.

        Returns ``True`` if the client is ready, ``False`` if initialisation
        failed (package missing or import error), in which case ``_enabled``
        is set to ``False`` to suppress further attempts.
        """
        if self._client is not None:
            return True

        try:
            from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

            self._client = InfluxDBClientAsync(
                url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
            )
            self._write_api = self._client.write_api()
            logger.info("InfluxDB async client initialised — %s", INFLUX_URL)
            return True

        except ImportError:
            logger.warning("influxdb-client not installed — InfluxDB writes disabled")
            self._enabled = False
            return False

        except Exception as exc:
            logger.warning("InfluxDB client init failed: %s", exc)
            self._enabled = False
            return False

    # ── Point construction ────────────────────────────────────────────────────

    def _build_points(self, snapshot: dict) -> dict[str, list]:
        """
        Convert a telemetry *snapshot* into InfluxDB ``Point`` objects grouped
        by target bucket.

        Returns ``{"telemetry": [...], "atmosphere": [...]}``.

        The method imports ``Point`` and ``WritePrecision`` locally so that a
        missing ``influxdb-client`` package does not prevent the module from
        loading.
        """
        try:
            from influxdb_client import Point, WritePrecision
        except ImportError:
            return {"telemetry": [], "atmosphere": []}

        ts_ns = int(time.time_ns())
        tel_points: list = []
        atm_points: list = []

        # Per-dish telemetry — one point per online antenna per frame.
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

        # Array-level summary — one point per frame regardless of dish count.
        tel_points.append(
            Point("array_summary")
            .tag(
                "obs_mode",
                snapshot.get("system", {}).get("obs_mode", "interferometry"),
            )
            .field("online_count", int(alma.get("online_count", 0)))
            .field("avg_tsys_k", float(alma.get("avg_tsys_k") or 0))
            .time(ts_ns, WritePrecision.NANOSECONDS)
        )

        # Atmospheric measurements — written to a separate bucket so that
        # retention policies and continuous queries can be applied
        # independently from the high-frequency dish telemetry.
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

    # ── Public write interface ────────────────────────────────────────────────

    async def write(self, snapshot: dict) -> None:
        """
        Accumulate *snapshot* into the pending buffer and flush when either
        the batch size or the flush interval threshold is exceeded.

        This coroutine is safe to await on every telemetry tick.  It returns
        immediately when the writer is disabled or when neither flush threshold
        has been reached.  It never raises; all exceptions are caught,
        counted, and logged.
        """
        if not self._enabled:
            return

        if not await self._ensure_client():
            return

        self._frame_count += 1
        grouped = self._build_points(snapshot)
        self._pending["telemetry"].extend(grouped["telemetry"])
        self._pending["atmosphere"].extend(grouped["atmosphere"])

        now = time.time()
        total_pending = sum(len(v) for v in self._pending.values())
        should_flush = (
            total_pending >= _BATCH_SIZE or (now - self._last_flush) >= _FLUSH_INTERVAL
        )

        if should_flush and total_pending:
            await self._flush()

    # ── Internal flush ────────────────────────────────────────────────────────

    async def _flush(self) -> None:
        """
        Write all buffered points to InfluxDB using the persistent client.

        The buffer is snapshotted and cleared before the network call so that
        points accumulated during an in-flight flush are not lost.  The
        persistent ``_write_api`` is reused across calls; a new HTTP request
        is issued per bucket, but the underlying connection pool is kept alive
        by the ``InfluxDBClientAsync`` instance.

        Write failures increment ``_error_count`` and update ``_last_error``
        but are otherwise suppressed.  Log output is throttled to one message
        per 60 consecutive failures to prevent log flooding during a prolonged
        InfluxDB outage.
        """
        total = sum(len(v) for v in self._pending.values())
        if total == 0:
            return

        # Snapshot and clear atomically (cooperative — no lock needed).
        to_write = {k: v[:] for k, v in self._pending.items()}
        for v in self._pending.values():
            v.clear()
        self._last_flush = time.time()

        bucket_map = {
            "telemetry": INFLUX_BUCKET,
            "atmosphere": INFLUX_ATM_BUCKET,
        }

        try:
            for key, points in to_write.items():
                if not points:
                    continue
                await self._write_api.write(bucket=bucket_map[key], record=points)
                logger.debug(
                    "InfluxDB: wrote %d points → %s", len(points), bucket_map[key]
                )

        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            if self._error_count % 60 == 1:
                logger.warning(
                    "InfluxDB write failed (%dx): %s", self._error_count, exc
                )
            # Attempt to recover a broken client on the next write cycle by
            # discarding the current instance.  The next call to
            # ``_ensure_client`` will create a fresh one.
            if self._error_count % 300 == 0:
                logger.warning(
                    "InfluxDB: resetting client after %d consecutive errors",
                    self._error_count,
                )
                await self._reset_client()

    async def _reset_client(self) -> None:
        """
        Close the existing client and clear instance references so that the
        next ``_ensure_client`` call creates a fresh connection.
        """
        try:
            if self._client is not None:
                await self._client.close()
        except Exception:
            pass
        finally:
            self._client = None
            self._write_api = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """
        Flush remaining buffered points and close the underlying HTTP client.

        Should be called from the ASGI lifespan shutdown hook to avoid data
        loss on graceful application restart.
        """
        total = sum(len(v) for v in self._pending.values())
        if total:
            logger.info("InfluxDB: flushing %d remaining points on shutdown", total)
            await self._flush()

        if self._client is not None:
            try:
                await self._client.close()
                logger.info("InfluxDB client closed")
            except Exception as exc:
                logger.warning("Error closing InfluxDB client: %s", exc)
            finally:
                self._client = None
                self._write_api = None

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a JSON-serialisable summary for the /health and /api/influx/status endpoints."""
        return {
            "enabled": self._enabled,
            "url": INFLUX_URL if self._enabled else None,
            "org": INFLUX_ORG if self._enabled else None,
            "buckets": (
                {"telemetry": INFLUX_BUCKET, "atmosphere": INFLUX_ATM_BUCKET}
                if self._enabled
                else None
            ),
            "client_alive": self._client is not None,
            "frames_seen": self._frame_count,
            "pending": {k: len(v) for k, v in self._pending.items()},
            "error_count": self._error_count,
            "last_error": self._last_error,
        }


# ── Module-level singleton ────────────────────────────────────────────────────
influx_writer = InfluxWriter()
