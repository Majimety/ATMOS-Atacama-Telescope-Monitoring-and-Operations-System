"""
atmosphere.py — REST endpoint สำหรับอ่าน atmospheric data
"""
from fastapi import APIRouter
from app.simulation.weather_fetcher import fetch_chajnantor_weather
from app.simulation.atmosphere_sim import simulate_atmosphere

router = APIRouter(prefix="/api/atmosphere", tags=["atmosphere"])


@router.get("/current")
async def get_atmosphere():
    """
    คืน atmospheric data ปัจจุบัน
    ลองดึงจาก Open-Meteo ก่อน ถ้าล้มเหลวใช้ simulation
    """
    try:
        weather = await fetch_chajnantor_weather()
        if weather:
            return {
                "temp_c": weather.temperature_c,
                "humidity_pct": weather.humidity_pct,
                "wind_ms": weather.wind_ms,
                "wind_dir_deg": weather.wind_dir_deg,
                "pressure_hpa": weather.pressure_hpa,
                "pwv_mm": weather.pwv_mm,
                "tau_225ghz": weather.tau_225ghz,
                "seeing_arcsec": weather.seeing_arcsec,
                "source": weather.source,
            }
    except Exception:
        pass

    return simulate_atmosphere()


@router.get("/pwv/history")
def get_pwv_history():
    """
    Placeholder — InfluxDB integration ใส่ตรงนี้ในอนาคต
    ตอนนี้คืน empty list
    """
    return {"points": [], "note": "InfluxDB integration pending"}
