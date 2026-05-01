"""
alma_sim.py — ALMA simulation engine ที่ใช้ข้อมูลจริง
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


def _build_array_from_real_pads() -> list[dict]:
    antennas = []
    for i, (pad, east_m, north_m, diam_m, ant_type) in enumerate(ALMA_REAL_PADS):
        is_faulted = (hash(pad) % 100) < 3

        antennas.append(
            {
                "id": pad,
                "type": ant_type,
                "east_m": east_m,
                "north_m": north_m,
                "x": east_m,
                "z": -north_m,
                "diameter_m": diam_m,
                "online": not is_faulted,
                "faulted": is_faulted,
                "ant_type": ant_type,
            }
        )
    return antennas


ANTENNA_ARRAY = _build_array_from_real_pads()

_pointing: dict[str, DishPointing] = {
    ant["id"]: DishPointing(ant["id"], az0=0.0, el0=45.0) for ant in ANTENNA_ARRAY
}

_system_state = {
    "band": 6,
    "obs_mode": "interferometry",
    "az_commanded": 183.7,
    "el_commanded": 52.4,
    "target_name": "Sgr A*",
    "target_ra": "17h 45m 40.04s",
    "target_dec": "-29° 00′ 28.1″",
    "pointing_mode": "tracking",
    "last_update_t": time.time(),
}

_injected_faults: set[str] = set()

_last_weather: WeatherData | None = None


def cmd_slew(az_deg: float, el_deg: float, target_name: str = "Custom"):
    _system_state["az_commanded"] = az_deg
    _system_state["el_commanded"] = el_deg
    _system_state["target_name"] = target_name
    _system_state["pointing_mode"] = "slewing"

    for p in _pointing.values():
        p.command_slew(az_deg, el_deg)


def cmd_stow():
    _system_state["pointing_mode"] = "stow"
    for p in _pointing.values():
        p.command_stow()


def cmd_set_band(band: int):
    if 1 <= band <= 10:
        _system_state["band"] = band


def cmd_set_mode(mode: str):
    _system_state["obs_mode"] = mode


def cmd_inject_fault(dish_id: str, offline: bool = True):
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


async def get_system_snapshot() -> dict:
    global _last_weather

    now = time.time()
    dt = now - _system_state["last_update_t"]
    _system_state["last_update_t"] = now

    try:
        weather = await asyncio.wait_for(fetch_chajnantor_weather(), timeout=3.0)
        _last_weather = weather
    except asyncio.TimeoutError:
        weather = _last_weather or _get_fallback_weather()

    band = _system_state["band"]
    tau = weather.tau_225ghz

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

        az, el = pointing.update(dt, now)
        online_count += 1

        tsys = compute_tsys(
            band=band,
            tau_225ghz=tau,
            elevation_deg=el,
        )
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

    modes = {_pointing[a["id"]].state for a in ANTENNA_ARRAY if a["online"]}
    if "slewing" in modes:
        _system_state["pointing_mode"] = "slewing"
    elif "settling" in modes:
        _system_state["pointing_mode"] = "settling"
    else:
        _system_state["pointing_mode"] = "tracking"

    avg_tsys = round(sum(tsys_values) / len(tsys_values), 1) if tsys_values else 0.0

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
            "weather_source": weather.source,
        },
    }


def _get_fallback_weather() -> WeatherData:
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
