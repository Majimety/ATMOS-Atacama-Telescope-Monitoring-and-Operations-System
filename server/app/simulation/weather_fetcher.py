"""
weather_fetcher.py — ดึงข้อมูลอากาศจริงจาก Chajnantor plateau

แหล่งข้อมูล:
  - Open-Meteo API (ฟรี ไม่ต้อง API key)
  - พิกัด ALMA / Chajnantor: lat=-23.0193, lon=-67.7532, alt=5058m

ข้อมูลที่ได้จริง:
  - temperature_2m       : °C
  - relative_humidity_2m : %
  - wind_speed_10m       : km/h → แปลงเป็น m/s
  - wind_direction_10m   : °
  - surface_pressure     : hPa
  - precipitation        : mm
  - cloud_cover          : %

ข้อมูลที่ derive จากสูตร physics จริง:
  - PWV (Precipitable Water Vapor)  : mm  — จาก RH + T + P
  - τ₂₂₅GHz (opacity)              : nepers — จาก PWV
  - Tsys estimated                  : K  — จาก τ + elevation
"""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


logger = logging.getLogger(__name__)

# ALMA / Chajnantor plateau coordinates
CHAJNANTOR_LAT = -23.0193
CHAJNANTOR_LON = -67.7532
CHAJNANTOR_ALT = 5058  # meters above sea level

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={CHAJNANTOR_LAT}"
    f"&longitude={CHAJNANTOR_LON}"
    f"&elevation={CHAJNANTOR_ALT}"
    "&current=temperature_2m,relative_humidity_2m,"
    "wind_speed_10m,wind_direction_10m,"
    "surface_pressure,precipitation,cloud_cover,weather_code"
    "&wind_speed_unit=ms"  # ขอ m/s โดยตรง
    "&timezone=America%2FSantiago"
)

# Cache อายุ 5 นาที — API ไม่อัพเดทถี่กว่านี้
CACHE_TTL_SECONDS = 300


@dataclass
class WeatherData:
    """ข้อมูลอากาศจริง + derived quantities สำหรับ SCADA"""

    # จาก API โดยตรง
    temperature_c: float = -8.0
    humidity_pct: float = 3.5
    wind_ms: float = 14.0
    wind_dir_deg: float = 270.0
    pressure_hpa: float = 545.0  # ความดันบน plateau ~540-560 hPa
    precipitation_mm: float = 0.0
    cloud_cover_pct: float = 0.0
    weather_code: int = 0

    # Derived จาก physics
    pwv_mm: float = 0.5  # Precipitable Water Vapor
    tau_225ghz: float = 0.05  # Atmospheric opacity ที่ 225 GHz
    seeing_arcsec: float = 0.8  # Optical/mm seeing

    # Metadata
    source: str = "simulation"  # "live" | "cached" | "simulation"
    fetched_at: float = field(default_factory=time.time)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > CACHE_TTL_SECONDS


def derive_pwv_from_meteo(
    temp_c: float,
    humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """
    คำนวณ PWV (Precipitable Water Vapor) จากค่า met จริง

    สูตร: PWV = scale_height × ρ_water_vapor

    ใช้ Clausius-Clapeyron ในการหา saturation vapor pressure,
    จากนั้นคำนวณ column density ของน้ำตาม hydrostatic equilibrium

    Reference: Pardo et al. 2001, ATM model; Otarola et al. 2010
    """
    # Saturation vapor pressure (Tetens formula, hPa)
    e_sat = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))

    # Actual vapor pressure
    e = (humidity_pct / 100.0) * e_sat

    # Water vapor density (g/m³) ที่ระดับพื้น
    # จาก ideal gas law: ρ = e × M_w / (R × T_K)
    T_K = temp_c + 273.15
    M_w = 18.015  # g/mol
    R = 8.314  # J/(mol·K)
    rho_water = (e * 100 * M_w) / (R * T_K)  # g/m³

    # Scale height ของ water vapor ใน atmosphere ~ 2000m
    # ที่ Atacama ความสูง 5058m เราอยู่เหนือ most of the water vapor แล้ว
    # ปรับ scale height ด้วย barometric factor
    pressure_ratio = pressure_hpa / 1013.25
    scale_height_m = 2000 * math.sqrt(pressure_ratio)

    # PWV = ρ × H_wv / ρ_liquid_water (แปลงเป็น mm)
    # density น้ำเหลว = 1000 kg/m³ = 1e6 g/m³ → ÷ 1e3 เพื่อให้ได้ mm
    rho_liquid = 1.0e6  # g/m³
    pwv_m = (rho_water * scale_height_m) / rho_liquid
    pwv_mm = pwv_m * 1000

    return max(0.05, min(pwv_mm, 20.0))


def derive_tau_from_pwv(pwv_mm: float) -> float:
    """
    คำนวณ opacity (τ) ที่ 225 GHz จาก PWV

    สูตรเชิง empirical จาก Danese & Partridge (1989) และ Otarola et al. (2010):
      τ₂₂₅ = τ_dry + B × PWV

    τ_dry = 0.030  (dry air contribution)
    B     = 0.058  nepers/mm  (wet term coefficient ที่ 225 GHz)

    Reference: ALMA Memo 271; ALMA Technical Handbook Sec. 9.1.2
    """
    tau_dry = 0.030
    B = 0.058
    return tau_dry + B * pwv_mm


def derive_seeing(wind_ms: float, pwv_mm: float, cloud_pct: float) -> float:
    """
    Estimate mm-wave seeing (phase coherence) จาก met parameters

    ค่า nominal Atacama: 0.4-1.2 arcsec
    เพิ่มขึ้นตาม wind (turbulence) และ PWV (wet layer)
    """
    base_seeing = 0.45
    wind_factor = max(0, (wind_ms - 8) * 0.012)
    pwv_factor = max(0, (pwv_mm - 0.5) * 0.08)
    cloud_factor = cloud_pct * 0.003
    return round(base_seeing + wind_factor + pwv_factor + cloud_factor, 2)


# Cache อยู่ใน module scope — shared ระหว่าง requests ทั้งหมด
_cached_weather: Optional[WeatherData] = None
_fetch_lock = asyncio.Lock()


async def fetch_chajnantor_weather() -> WeatherData:
    """
    ดึงข้อมูลอากาศจริงจาก Open-Meteo API
    ถ้า cache ยังใช้ได้ return cache ทันที
    ถ้า API ล้มเหลว fall back เป็น simulation ที่สมจริง
    """
    global _cached_weather

    # ส่ง cache ถ้ายังไม่ stale
    if _cached_weather and not _cached_weather.is_stale:
        return _cached_weather

    async with _fetch_lock:
        # ตรวจอีกครั้งหลัง acquire lock (double-checked locking)
        if _cached_weather and not _cached_weather.is_stale:
            return _cached_weather

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(OPEN_METEO_URL)
                response.raise_for_status()
                data = response.json()

            current = data["current"]

            temp_c = current["temperature_2m"]
            humidity = current["relative_humidity_2m"]
            wind_ms = current["wind_speed_10m"]
            wind_dir = current["wind_direction_10m"]
            pressure = current["surface_pressure"]
            precip = current["precipitation"]
            cloud = current["cloud_cover"]
            wcode = current["weather_code"]

            # Derive physics quantities
            pwv = derive_pwv_from_meteo(temp_c, humidity, pressure)
            tau = derive_tau_from_pwv(pwv)
            seeing = derive_seeing(wind_ms, pwv, cloud)

            weather = WeatherData(
                temperature_c=round(temp_c, 1),
                humidity_pct=round(humidity, 1),
                wind_ms=round(wind_ms, 1),
                wind_dir_deg=round(wind_dir, 0),
                pressure_hpa=round(pressure, 1),
                precipitation_mm=round(precip, 2),
                cloud_cover_pct=round(cloud, 0),
                weather_code=wcode,
                pwv_mm=round(pwv, 3),
                tau_225ghz=round(tau, 4),
                seeing_arcsec=seeing,
                source="live",
                fetched_at=time.time(),
            )

            _cached_weather = weather
            logger.info(
                f"[weather] LIVE T={temp_c}°C RH={humidity}% "
                f"Wind={wind_ms}m/s PWV={pwv:.3f}mm τ={tau:.4f}"
            )
            return weather

        except Exception as exc:
            logger.warning(
                f"[weather] API fetch failed ({exc}) — using simulation fallback"
            )
            return _simulate_chajnantor_weather()


def _simulate_chajnantor_weather() -> WeatherData:
    """
    Fallback simulation ถ้า API ล้มเหลว
    ใช้ค่าที่อิงจาก climatology จริงของ Chajnantor
    (Otarola et al. 2010, Table 2 — median values)
    """
    t = time.time()

    # Diurnal cycle จริง: temperature ต่ำสุดช่วงรุ่งเช้า สูงสุดบ่าย
    hour_utc = (t / 3600) % 24
    # Chajnantor อยู่ UTC-3 โดยประมาณ
    local_hour = (hour_utc - 3) % 24
    diurnal = math.sin((local_hour - 6) / 24 * 2 * math.pi)

    temp_c = -7.5 + diurnal * 6.0 + math.sin(t * 0.001) * 0.5
    humidity = 3.0 + diurnal * 2.0 + math.sin(t * 0.003) * 0.3
    wind_ms = (
        13.5
        + math.sin(t * 0.007) * 4.0
        + (
            # wind มักสูงกว่าในช่วงบ่าย
            3.0
            if 10 < local_hour < 18
            else 0.0
        )
    )
    pressure = 542.0 + math.sin(t * 0.0005) * 2.0
    cloud = max(0, 2.0 + math.sin(t * 0.002) * 1.5)

    pwv = derive_pwv_from_meteo(temp_c, humidity, pressure)
    tau = derive_tau_from_pwv(pwv)
    seeing = derive_seeing(wind_ms, pwv, cloud)

    return WeatherData(
        temperature_c=round(temp_c, 1),
        humidity_pct=round(max(0.5, humidity), 1),
        wind_ms=round(max(0, wind_ms), 1),
        wind_dir_deg=round(270 + math.sin(t * 0.004) * 30, 0),
        pressure_hpa=round(pressure, 1),
        precipitation_mm=0.0,
        cloud_cover_pct=round(cloud, 0),
        weather_code=0,
        pwv_mm=round(pwv, 3),
        tau_225ghz=round(tau, 4),
        seeing_arcsec=seeing,
        source="simulation",
        fetched_at=time.time(),
    )
