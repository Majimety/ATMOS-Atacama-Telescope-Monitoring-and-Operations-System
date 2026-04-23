from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api import WriteOptions
from influxdb_client import Point
import os, asyncio

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "atmos")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "telemetry")


async def write_telemetry(frame: dict):
    """Call this from your telemetry loop to persist every frame."""
    async with InfluxDBClientAsync(
        url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
    ) as client:
        write_api = client.write_api()
        points = []
        for dish in frame.get("dishes", []):
            p = (
                Point("dish_telemetry")
                .tag("dish_id", dish["id"])
                .tag("array", dish.get("array", "ALMA"))
                .field("tsys", dish.get("tsys", 0.0))
                .field("azimuth", dish.get("az", 0.0))
                .field("elevation", dish.get("el", 0.0))
                .field("status", 1 if dish.get("status") == "online" else 0)
            )
            points.append(p)

        atm = frame.get("atmosphere", {})
        points.append(
            Point("atmosphere")
            .field("pwv_mm", atm.get("pwv", 0.0))
            .field("tau_225ghz", atm.get("tau225", 0.0))
            .field("wind_ms", atm.get("windSpeed", 0.0))
            .field("temperature_k", atm.get("temperature", 273.0))
        )
        await write_api.write(bucket=INFLUX_BUCKET, record=points)
