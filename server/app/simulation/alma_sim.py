"""
alma_sim.py — ALMA simulation engine ที่ใช้ข้อมูลจริง

ข้อมูลจริงที่ใช้:
  1. ตำแหน่ง pad จริงจาก ALMA C43 config (CASA/NRAO public data)
  2. สภาพอากาศจริงจาก Open-Meteo API (ดึงทุก 5 นาที)

Physical models:
  3. Tsys = f(T_rx_spec, τ_band, airmass)  — radiometry equation จริง
  4. τ_band = τ_scale × τ_225              — scaling จาก atmospheric model
  5. PWV → τ_225                            — Danese & Partridge (1989)
  6. PWV ← RH, T, P                        — Clausius-Clapeyron + hydrostatics
  7. Slew rate 3°/s az / 1.5°/s el         — ALMA TRE spec จริง
  8. Tracking error < 0.6 arcsec RMS       — ALMA pointing spec จริง

"""

import asyncio
import math
import random
import time
from datetime import datetime, timezone

from .alma_positions import ALMA_REAL_PADS, CHAJNANTOR_TELESCOPES
from .weather_fetcher import (
    fetch_chajnantor_weather,
    WeatherData,
    derive_pwv_from_meteo,
    derive_tau_from_pwv,
)
from .physics_models import (
    compute_tsys,
    compute_signal_level_dbm,
    DishPointing,
    ALMA_RECEIVER_TEMP,
)


# ── Build antenna array from real pad positions ───────────────────────────────


def _build_array_from_real_pads() -> list[dict]:
    """
    แปลง pad positions จาก ENU (m) เป็น format ที่ใช้ใน simulation
    กำหนด antenna ว่า online/offline ตาม realistic fault rate
    """
    antennas = []
    for i, (pad, east_m, north_m, diam_m, ant_type) in enumerate(ALMA_REAL_PADS):
        # Realistic fault rate: ~3% ของ array offline ตลอดเวลา
        # ใช้ hash เพื่อให้ fault pattern คงที่ (ไม่ random ทุก restart)
        is_faulted = (hash(pad) % 100) < 3

        antennas.append(
            {
                "id": pad,
                "type": ant_type,
                "east_m": east_m,  # ตำแหน่งจริงใน ENU
                "north_m": north_m,  # ตำแหน่งจริงใน ENU
                "x": east_m,  # alias สำหรับ 3D scene
                "z": -north_m,  # Three.js ใช้ Z=-North
                "diameter_m": diam_m,
                "online": not is_faulted,
                "faulted": is_faulted,
                "ant_type": ant_type,  # DA, DV, PM, CM (ACA)
            }
        )
    return antennas


ANTENNA_ARRAY = _build_array_from_real_pads()

# สร้าง DishPointing object 1 ตัวต่อ 1 antenna — จัดการ slew/track จริง
_pointing: dict[str, DishPointing] = {
    ant["id"]: DishPointing(ant["id"], az0=0.0, el0=45.0) for ant in ANTENNA_ARRAY
}

# State ของระบบ
_system_state = {
    "band": 6,
    "obs_mode": "interferometry",
    "az_commanded": 183.7,  # Sgr A* default
    "el_commanded": 52.4,
    "target_name": "Sgr A*",
    "target_ra": "17h 45m 40.04s",
    "target_dec": "-29° 00′ 28.1″",
    "pointing_mode": "tracking",
    "last_update_t": time.time(),
}

# Faults ที่ inject จากนอก (เพิ่มได้จาก REST API)
_injected_faults: set[str] = set()

# Weather cache สำหรับ background refresh
_last_weather: WeatherData | None = None
_weather_task: asyncio.Task | None = None


# ── Public commands (เรียกจาก WebSocket handler) ──────────────────────────────


def cmd_slew(az_deg: float, el_deg: float, target_name: str = "Custom"):
    """สั่งให้ทุก dish หมุนไปยัง az/el ที่กำหนด"""
    _system_state["az_commanded"] = az_deg
    _system_state["el_commanded"] = el_deg
    _system_state["target_name"] = target_name
    _system_state["pointing_mode"] = "slewing"

    for p in _pointing.values():
        p.command_slew(az_deg, el_deg)


def cmd_stow():
    """Stow position: Az 0°, El 15°"""
    _system_state["pointing_mode"] = "stow"
    for p in _pointing.values():
        p.command_stow()


def cmd_set_band(band: int):
    if 1 <= band <= 10:
        _system_state["band"] = band


def cmd_set_mode(mode: str):
    _system_state["obs_mode"] = mode


def cmd_inject_fault(dish_id: str, offline: bool = True):
    """จำลอง hardware fault ใน dish ที่ระบุ
    offline=True  → ทำให้ dish ออฟไลน์
    offline=False → clear fault (เทียบเท่า cmd_clear_fault)
    """
    if offline:
        _injected_faults.add(dish_id)
        for ant in ANTENNA_ARRAY:
            if ant["id"] == dish_id:
                ant["online"] = False
    else:
        cmd_clear_fault(dish_id)


def cmd_clear_fault(dish_id: str):
    _injected_faults.discard(dish_id)
    for ant in ANTENNA_ARRAY:
        if ant["id"] == dish_id and not ant["faulted"]:
            ant["online"] = True


# ── Main snapshot builder ─────────────────────────────────────────────────────


async def get_system_snapshot() -> dict:
    """
    สร้าง snapshot ของระบบทั้งหมด
    เรียกทุก 1 วินาทีจาก WebSocket handler
    """
    global _last_weather

    now = time.time()
    dt = now - _system_state["last_update_t"]
    _system_state["last_update_t"] = now

    # ── ดึงข้อมูลอากาศจริง (non-blocking, cached 5 min) ──────────────────────
    try:
        weather = await asyncio.wait_for(fetch_chajnantor_weather(), timeout=3.0)
        _last_weather = weather
    except asyncio.TimeoutError:
        weather = _last_weather or _get_fallback_weather()

    band = _system_state["band"]
    tau = weather.tau_225ghz

    # ── อัพเดท pointing ของทุก dish ──────────────────────────────────────────
    dish_states = []
    online_count = 0
    tsys_values = []

    for ant in ANTENNA_ARRAY:
        pointing = _pointing[ant["id"]]

        if not ant["online"]:
            dish_states.append(
                {
                    "id": ant["id"],
                    "type": ant["type"],
                    "x": ant["x"],
                    "z": ant["z"],
                    "east_m": ant["east_m"],
                    "north_m": ant["north_m"],
                    "diameter_m": ant["diameter_m"],
                    "online": False,
                    "az_deg": 0.0,
                    "el_deg": 15.0,
                    "tsys_k": None,
                    "signal_dbm": None,
                    "pointing_mode": "stow",
                }
            )
            continue

        # อัพเดท pointing ตาม slew physics
        az, el = pointing.update(dt, now)
        online_count += 1

        # คำนวณ Tsys จาก physical model จริง
        tsys = compute_tsys(
            band=band,
            tau_225ghz=tau,
            elevation_deg=el,
        )
        # เพิ่ม noise เล็กน้อยต่าง dish ต่าง phase
        phase = hash(ant["id"]) % 1000
        tsys += math.sin(now * 0.003 + phase * 0.1) * 1.5 + random.gauss(0, 0.4)
        tsys = round(max(20, tsys), 1)
        tsys_values.append(tsys)

        signal = compute_signal_level_dbm(tsys, el, band)

        dish_states.append(
            {
                "id": ant["id"],
                "type": ant["type"],
                "x": ant["x"],
                "z": ant["z"],
                "east_m": ant["east_m"],
                "north_m": ant["north_m"],
                "diameter_m": ant["diameter_m"],
                "online": True,
                "az_deg": az,
                "el_deg": el,
                "tsys_k": tsys,
                "signal_dbm": signal,
                "pointing_mode": pointing.pointing_mode,
            }
        )

    # อัพเดท overall pointing_mode
    modes = {_pointing[a["id"]].state for a in ANTENNA_ARRAY if a["online"]}
    if "slewing" in modes:
        _system_state["pointing_mode"] = "slewing"
    elif "settling" in modes:
        _system_state["pointing_mode"] = "settling"
    else:
        _system_state["pointing_mode"] = "tracking"

    avg_tsys = round(sum(tsys_values) / len(tsys_values), 1) if tsys_values else 0.0

    # ── Band frequency map ────────────────────────────────────────────────────
    band_freq = {
        1: 43,
        2: 67,
        3: 100,
        4: 144,
        5: 183,
        6: 230,
        7: 345,
        8: 397,
        9: 650,
        10: 870,
    }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commanded_target": {
            "name": _system_state["target_name"],
            "az_deg": _system_state["az_commanded"],
            "el_deg": _system_state["el_commanded"],
            "ra": _system_state["target_ra"],
            "dec": _system_state["target_dec"],
        },
        "pointing_mode": _system_state["pointing_mode"],
        "system": {
            "band": band,
            "freq_ghz": band_freq[band],
            "obs_mode": _system_state["obs_mode"],
            "fault_count": len(ANTENNA_ARRAY) - online_count,
        },
        "alma": {
            "dishes": dish_states,
            "online_count": online_count,
            "total_count": len(ANTENNA_ARRAY),
            "avg_tsys_k": avg_tsys,
        },
        # large_telescopes ยังคง format เดิมเพื่อ compatibility กับ Scene.jsx
        "large_telescopes": [
            {
                **tel,
                "x": tel["x_m"],
                "z": -tel.get("y_m", 0),
                "diameter_m": tel["diameter_m"],
            }
            for tel in CHAJNANTOR_TELESCOPES
        ],
        "atmosphere": {
            # ข้อมูลจริงจาก API (หรือ simulation fallback)
            "pwv_mm": weather.pwv_mm,
            "tau_225ghz": weather.tau_225ghz,
            "wind_ms": weather.wind_ms,
            "wind_dir_deg": weather.wind_dir_deg,
            "temp_c": weather.temperature_c,
            "humidity_pct": weather.humidity_pct,
            "pressure_hpa": weather.pressure_hpa,
            "cloud_cover_pct": weather.cloud_cover_pct,
            "seeing_arcsec": weather.seeing_arcsec,
            "precipitation_mm": weather.precipitation_mm,
            "weather_source": weather.source,  # "live" | "simulation"
        },
    }


def _get_fallback_weather() -> WeatherData:
    """สำรองสุดท้าย ถ้า fetch ไม่ได้เลย"""
    pwv = derive_pwv_from_meteo(-8.0, 3.5, 542.0)
    return WeatherData(
        temperature_c=-8.0,
        humidity_pct=3.5,
        wind_ms=14.0,
        wind_dir_deg=270.0,
        pressure_hpa=542.0,
        pwv_mm=pwv,
        tau_225ghz=derive_tau_from_pwv(pwv),
        seeing_arcsec=0.6,
        source="simulation",
    )
