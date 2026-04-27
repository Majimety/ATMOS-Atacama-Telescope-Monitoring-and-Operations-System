#!/usr/bin/env python3
"""
seed.py — Seed InfluxDB ด้วยข้อมูล telemetry จำลอง 24 ชั่วโมงย้อนหลัง
ใช้สำหรับ dev/demo เพื่อให้ Grafana มีข้อมูลแสดงทันที

Usage:
  pip install influxdb-client python-dotenv
  INFLUX_URL=http://localhost:8086 INFLUX_TOKEN=<token> INFLUX_ORG=atmos python seed.py
"""
import os
import math
import random
import time
from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "atmos-dev-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "atmos")
BUCKET_TEL = "atmos_telemetry"
BUCKET_ATM = "atmos_atmosphere"

# Measurements written here must stay in sync with influx_writer.py:
#   dish_telemetry  — per-dish fields: az_deg, el_deg, tsys_k, signal_dbm, online
#   array_summary   — online_count, avg_tsys_k
#   atmosphere      — pwv_mm, tau_225ghz, wind_ms, temp_c, humidity_pct, pressure_hpa
#
# Note: the live WebSocket frame also carries a `scheduler` block, but that is
# transient state (active job, queue, history) and is NOT written to InfluxDB.

DISH_IDS = (
    [f"A{i:03d}" for i in range(1, 7)]
    + [f"B{i:03d}" for i in range(1, 15)]
    + [f"C{i:03d}" for i in range(1, 15)]
    + [f"D{i:03d}" for i in range(1, 15)]
    + [f"ACA{i:02d}" for i in range(1, 13)]
)


def main():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    step = timedelta(
        seconds=60
    )  # 1 point per minute (not 1Hz — too much data for seed)

    points = []
    t = start
    while t <= now:
        ts = t
        # Simulate atmosphere
        diurnal = math.sin(2 * math.pi * t.timestamp() / 86400)
        pwv = max(0.1, 0.5 + diurnal * 0.15 + random.gauss(0, 0.03))
        wind = max(0, 8 + math.sin(t.timestamp() / 600) * 3 + random.gauss(0, 0.5))
        # Match influx_writer formula: τ₂₂₅ ≈ 0.04·PWV + 0.012 (Pardo 2001)
        tau = max(0.01, 0.04 * pwv + 0.012)

        points.append(
            Point("atmosphere")
            .field("pwv_mm", pwv)
            .field("tau_225ghz", tau)
            .field("wind_ms", wind)
            .field("temp_c", -8 + diurnal * 4)
            .field("humidity_pct", pwv * 8)
            .field("pressure_hpa", 545.0)
            .time(ts, WritePrecision.SECONDS)
        )

        online_dishes = []
        for dish_id in DISH_IDS:
            faulted = (hash(dish_id) % 100) < 3
            online = not faulted and random.random() > 0.005
            tsys = 65 + tau * 800 + random.gauss(0, 5) if online else None
            signal = -80 + random.gauss(0, 2) if online else None
            if online and tsys:
                online_dishes.append(tsys)

            p = (
                Point("dish_telemetry")
                .tag("dish_id", dish_id)
                .tag(
                    "ant_type",
                    (
                        "DA"
                        if dish_id.startswith("A")
                        else "CM" if dish_id.startswith("ACA") else "DV"
                    ),
                )
                .field("online", online)
                .field("az_deg", (180 + math.sin(t.timestamp() / 3600) * 10) % 360)
                .field("el_deg", 52.4 + math.cos(t.timestamp() / 7200) * 5)
                .time(ts, WritePrecision.SECONDS)
            )
            if tsys:
                p = p.field("tsys_k", tsys)
            if signal:
                p = p.field("signal_dbm", signal)
            points.append(p)

        # array_summary — mirrors what influx_writer.py writes each live tick
        avg_tsys = sum(online_dishes) / len(online_dishes) if online_dishes else 0.0
        points.append(
            Point("array_summary")
            .field("online_count", len(online_dishes))
            .field("avg_tsys_k", round(avg_tsys, 2))
            .time(ts, WritePrecision.SECONDS)
        )

        t += step

        if len(points) >= 5000:
            write_api.write(
                bucket=BUCKET_TEL,
                record=[
                    p for p in points if p._name in ("dish_telemetry", "array_summary")
                ],
            )
            write_api.write(
                bucket=BUCKET_ATM, record=[p for p in points if p._name == "atmosphere"]
            )
            print(f"Wrote {len(points)} points up to {t.isoformat()}")
            points = []

    if points:
        write_api.write(
            bucket=BUCKET_TEL,
            record=[
                p for p in points if p._name in ("dish_telemetry", "array_summary")
            ],
        )
        write_api.write(
            bucket=BUCKET_ATM, record=[p for p in points if p._name == "atmosphere"]
        )

    print(f"Seed complete — {(now - start).total_seconds() / 60:.0f} minutes of data")
    client.close()


if __name__ == "__main__":
    main()
