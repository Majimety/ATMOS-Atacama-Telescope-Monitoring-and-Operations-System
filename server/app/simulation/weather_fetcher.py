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

    สูตร: PWV = H_wv × ρ_wv(site)
      โดย integrate exponential profile จาก z_site ถึง ∞:
        PWV = ∫[z_site,∞] ρ(z) dz = ρ_site × H_wv

    Water vapor scale height ที่ Chajnantor:
      Giovanelli et al. 2001 (radiosonde): median H_wv ≈ 1.13 km
      Otarola et al. 2019 (PWV Peak/Plateau ratio): H_wv = 1.2–1.5 km
    ใช้ H_wv = 1300 m (กลาง range จาก observation จริง)

    หมายเหตุ: ρ_wv ที่วัดได้คือ in-situ density ณ z_site
    ดังนั้น PWV = ρ_wv(site) × H_wv  (column เหนือ site)

    Reference: Giovanelli et al. 2001, PASP; Otarola et al. 2010, PASP 122, 1333;
               Otarola et al. 2019, PASP 131
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

    # Water vapor scale height ที่ Chajnantor
    # Giovanelli 2001: median 1.13 km; Otarola 2019: 1.2–1.5 km
    H_wv = 1300.0  # m — scale height ที่ Chajnantor (1300 m = กลาง observed range)

    # PWV = ρ_wv × H_wv / ρ_liquid (column เหนือ site, แปลงเป็น mm)
    # density น้ำเหลว = 1e6 g/m³
    rho_liquid = 1.0e6  # g/m³
    pwv_mm = (rho_water * H_wv) / rho_liquid * 1000

    return max(0.05, min(pwv_mm, 20.0))


def derive_tau_from_pwv(pwv_mm: float) -> float:
    """
    คำนวณ opacity (τ) ที่ 225 GHz จาก PWV

    สูตรเชิง empirical สำหรับ Chajnantor plateau (alt ~5058 m):
      τ₂₂₅ = τ_dry + B × PWV

    τ_dry = 0.012  (dry air contribution ที่ระดับความสูง Chajnantor)
    B     = 0.040  nepers/mm  (wet term coefficient ที่ 225 GHz)

    ที่มา: Liebe 1989 / Masson 1989 พื้นฐาน τ = 0.01 + 0.04×PWV สำหรับ Mauna Kea
    ปรับ dry term เป็น 0.012 สำหรับ Chajnantor ตาม Otarola et al. (2010) ซึ่งได้
    inverse จาก PWV = 23.199×τ₂₂₅ − 0.3142 → τ₂₂₅ ≈ 0.04313×PWV + 0.01354
    ค่า τ_dry=0.012 และ B=0.040 ตรงกับ README และ ALMA Technical Handbook Sec. 9.1.2

    Reference: Liebe 1989; Masson 1989; Otarola et al. 2010, PASP 122, 1333
    """
    tau_dry = 0.012
    B = 0.040
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
_fetch_lock: Optional[asyncio.Lock] = None
_fetch_lock_init_lock: Optional[asyncio.Lock] = None


async def _get_fetch_lock() -> asyncio.Lock:
    """
    Lazy-init ทั้ง outer init-lock และ fetch-lock ภายใน running event loop
    (Python 3.10+ ห้ามสร้าง asyncio.Lock นอก running loop)

    Pattern: ใช้ asyncio.get_event_loop().run_in_executor เป็น tie-breaker ไม่ได้
    แต่ใน asyncio single-threaded: ถ้า None check ผ่านก่อน first await
    coroutine อื่นจะไม่ได้รัน → safe to init here (no context switch before assignment)
    """
    global _fetch_lock, _fetch_lock_init_lock
    if _fetch_lock is not None:
        return _fetch_lock
    # สร้าง init-lock ครั้งแรก — safe เพราะ Python asyncio เป็น single-threaded
    # ไม่มี context switch ระหว่าง if check กับ assignment (ไม่มี await ระหว่างนี้)
    if _fetch_lock_init_lock is None:
        _fetch_lock_init_lock = asyncio.Lock()
    async with _fetch_lock_init_lock:
        if _fetch_lock is None:
            _fetch_lock = asyncio.Lock()
    return _fetch_lock


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

    async with await _get_fetch_lock():
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
            sim = _simulate_chajnantor_weather()
            # set cache เพื่อให้ double-checked locking ทำงานได้
            # coroutine อื่นที่รอ lock จะเห็น cache fresh แล้ว → ไม่ fetch ซ้ำ
            _cached_weather = sim
            return sim


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
