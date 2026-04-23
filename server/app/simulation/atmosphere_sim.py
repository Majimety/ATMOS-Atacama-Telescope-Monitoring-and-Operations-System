"""
atmosphere_sim.py — Atmospheric opacity and PWV simulation
ใช้เป็น fallback เมื่อ weather_fetcher ไม่สามารถดึงข้อมูลจริงได้
"""
import math
import random
import time


# Typical Chajnantor conditions
_BASE_PWV = 0.5       # mm PWV baseline (excellent site)
_BASE_WIND = 8.0      # m/s baseline wind
_BASE_TEMP = -8.0     # °C


def simulate_atmosphere(t: float | None = None) -> dict:
    """
    จำลองสภาพอากาศที่ Chajnantor plateau แบบ time-varying

    ใช้ slow sinusoidal drift + small random noise
    เพื่อให้กราฟดู realistic (ไม่ใช่ random ขาวล้วน)
    """
    if t is None:
        t = time.time()

    # Diurnal variation — PWV สูงตอนบ่าย (ความร้อนนำน้ำขึ้น)
    diurnal = math.sin(2 * math.pi * t / 86400) * 0.15

    pwv = max(0.1, _BASE_PWV + diurnal + random.gauss(0, 0.03))
    wind = max(0, _BASE_WIND + math.sin(t / 600) * 3 + random.gauss(0, 0.5))
    temp = _BASE_TEMP + math.sin(2 * math.pi * t / 86400) * 4 + random.gauss(0, 0.3)

    # τ₂₂₅GHz ≈ 0.04 × PWV (Danese & Partridge approximation)
    tau = max(0.01, 0.04 * pwv + random.gauss(0, 0.002))

    return {
        "temp_c": round(temp, 2),
        "humidity_pct": round(max(1, min(100, pwv * 8)), 1),
        "wind_ms": round(wind, 2),
        "wind_dir_deg": round((270 + math.sin(t / 300) * 30) % 360, 1),
        "pressure_hpa": round(545 + random.gauss(0, 0.5), 1),
        "pwv_mm": round(pwv, 3),
        "tau_225ghz": round(tau, 4),
        "seeing_arcsec": round(max(0.3, 0.8 + random.gauss(0, 0.1)), 2),
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 0.0,
        "source": "simulation",
    }
