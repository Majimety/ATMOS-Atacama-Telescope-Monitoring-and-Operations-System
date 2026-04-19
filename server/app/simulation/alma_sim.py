import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


ARM_COUNT = 3
DISHES_PER_ARM = 20
ARM_START_ANGLE_DEG = 90

BAND_FREQ_GHZ = {
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

LARGE_TELESCOPES = [
    {
        "id": "apex",
        "name": "APEX 12m",
        "type": "single",
        "x": -180.0,
        "z": 80.0,
        "altitude_m": 5107,
        "diameter_m": 12,
        "online": True,
    },
    {
        "id": "iram",
        "name": "IRAM 30m",
        "type": "single",
        "x": 220.0,
        "z": -120.0,
        "altitude_m": 2850,
        "diameter_m": 30,
        "online": True,
    },
    {
        "id": "aste",
        "name": "ASTE 10m",
        "type": "single",
        "x": 140.0,
        "z": 250.0,
        "altitude_m": 4860,
        "diameter_m": 10,
        "online": True,
    },
    {
        "id": "nanten2",
        "name": "NANTEN2 4m",
        "type": "single",
        "x": -350.0,
        "z": 100.0,
        "altitude_m": 4865,
        "diameter_m": 4,
        "online": True,
    },
    {
        "id": "eht_alpha",
        "name": "EHT Node α",
        "type": "eht",
        "x": -280.0,
        "z": -200.0,
        "altitude_m": 5000,
        "diameter_m": 12,
        "online": True,
    },
    {
        "id": "eht_beta",
        "name": "EHT Node β",
        "type": "eht",
        "x": 300.0,
        "z": 180.0,
        "altitude_m": 5000,
        "diameter_m": 12,
        "online": False,
    },
]


# ── Array layout ─────────────────────────────────────────────────────────────


def _place_dishes_along_arm(arm_index: int) -> list[dict]:
    angle_rad = math.radians(ARM_START_ANGLE_DEG + arm_index * 120)
    dishes = []
    for i in range(DISHES_PER_ARM):
        # ระยะห่างเพิ่มแบบ non-linear เพื่อจำลอง baseline coverage จริง
        radius = 20 + i * 9 + (i**1.4)
        dishes.append(
            {
                "id": f"DA-{arm_index * DISHES_PER_ARM + i + 1:02d}",
                "arm": arm_index,
                "x": round(math.cos(angle_rad) * radius, 2),
                "z": round(math.sin(angle_rad) * radius, 2),
                "base_tsys_k": 55.0 + i * 1.2,
                "online": not (arm_index == 0 and i == 4),  # DA-05 fault simulation
            }
        )
    return dishes


def _place_center_dishes() -> list[dict]:
    positions = [(5, 5), (-5, 8), (8, -4), (-7, -5), (3, -9), (-4, 3)]
    return [
        {
            "id": f"DV-{idx + 1:02d}",
            "arm": -1,
            "x": float(x),
            "z": float(z),
            "base_tsys_k": 52.0,  # center dishes มี Tsys ดีกว่าเล็กน้อย
            "online": True,
        }
        for idx, (x, z) in enumerate(positions)
    ]


def build_alma_array() -> list[dict]:
    dishes = []
    for arm in range(ARM_COUNT):
        dishes.extend(_place_dishes_along_arm(arm))
    dishes.extend(_place_center_dishes())
    return dishes


# สร้าง array ครั้งเดียวตอน module load — ตำแหน่งไม่เปลี่ยน
ALMA_ARRAY = build_alma_array()


# ── System state ──────────────────────────────────────────────────────────────


@dataclass
class SystemState:
    """
    เก็บ mutable state ของระบบทั้งหมดไว้ใน object เดียว
    แทนที่จะกระจายเป็น global variables ซึ่งแก้ไขยากและ test ยาก
    """

    active_band: int = 6
    obs_mode: str = "interferometry"
    fault_overrides: dict[str, bool] = field(default_factory=dict)

    def set_band(self, band: int):
        self.active_band = max(1, min(10, band))

    def set_obs_mode(self, mode: str):
        self.obs_mode = mode

    def inject_fault(self, dish_id: str, offline: bool):
        self.fault_overrides[dish_id] = offline

    def dish_is_online(self, dish: dict) -> bool:
        if dish["id"] in self.fault_overrides:
            return not self.fault_overrides[dish["id"]]
        return dish["online"]


# singleton — ใช้ร่วมกันทั้ง app
system_state = SystemState()


# helper wrappers ให้ main.py และ telemetry.py เรียกได้เหมือนเดิม
def set_band(band: int):
    system_state.set_band(band)


def set_obs_mode(mode: str):
    system_state.set_obs_mode(mode)


def inject_fault(dish_id: str, offline: bool):
    system_state.inject_fault(dish_id, offline)


# ── Signal computation ────────────────────────────────────────────────────────


def _compute_dish_pointing(
    dish_id: str, az_commanded: float, el_commanded: float, t: float
) -> tuple[float, float]:
    # แต่ละ dish มี tracking error เฉพาะตัว ใช้ hash ของ id เป็น phase offset
    phase = hash(dish_id) % 1000
    az_error = math.sin(t * 0.1 + phase) * 0.05  # ~0.05° peak error
    el_error = math.cos(t * 0.13 + phase) * 0.03
    return round(az_commanded + az_error, 3), round(el_commanded + el_error, 3)


def _compute_tsys(base_tsys_k: float, dish_id: str, t: float, band: int) -> float:
    phase = hash(dish_id) % 1000
    # Tsys สูงขึ้นตาม band เพราะความถี่สูงกว่า = atmosphere opacity มากกว่า
    band_factor = 1.0 + (band - 1) * 0.15
    drift = math.sin(t * 0.005 + phase * 0.1) * 5.0
    noise = random.gauss(0, 0.8)
    return round((base_tsys_k + drift + noise) * band_factor, 1)


def _compute_signal_level_dbm(el_deg: float, band: int) -> float:
    # signal อ่อนลงเมื่อ elevation ต่ำ (airmass สูง) และ band สูง
    base = -12.0 + (el_deg - 45.0) * 0.05 - (band - 1) * 0.3
    return round(base + random.gauss(0, 0.2), 2)


# ── Per-dish sampling ─────────────────────────────────────────────────────────


def sample_dish_state(
    dish: dict, az_commanded: float, el_commanded: float, t: float
) -> dict:
    online = system_state.dish_is_online(dish)

    if not online:
        return {
            "id": dish["id"],
            "online": False,
            "x": dish["x"],
            "z": dish["z"],
            "az_deg": 0.0,
            "el_deg": 15.0,
            "tsys_k": None,
            "signal_dbm": None,
            "fault": True,
        }

    az, el = _compute_dish_pointing(dish["id"], az_commanded, el_commanded, t)
    tsys = _compute_tsys(dish["base_tsys_k"], dish["id"], t, system_state.active_band)

    return {
        "id": dish["id"],
        "online": True,
        "x": dish["x"],
        "z": dish["z"],
        "az_deg": az,
        "el_deg": el,
        "tsys_k": tsys,
        "signal_dbm": _compute_signal_level_dbm(el, system_state.active_band),
        "fault": False,
    }


def sample_atmosphere(t: float) -> dict:
    pwv_mm = 0.42 + math.sin(t * 0.002) * 0.15 + random.gauss(0, 0.01)
    wind_ms = 14.3 + math.sin(t * 0.007) * 3.5 + random.gauss(0, 0.3)
    temp_c = -8.1 + math.sin(t * 0.001) * 2.0
    humidity_pct = 3.2 + math.sin(t * 0.003) * 0.8
    tau = 0.03 + pwv_mm * 0.005

    return {
        "pwv_mm": round(max(0.1, pwv_mm), 3),
        "wind_ms": round(max(0.0, wind_ms), 1),
        "temp_c": round(temp_c, 1),
        "tau_225ghz": round(tau, 4),
        "humidity_pct": round(max(0.0, humidity_pct), 1),
        "seeing_arcsec": round(0.3 + tau * 8 + random.gauss(0, 0.02), 2),
    }


# ── Main snapshot ─────────────────────────────────────────────────────────────


def get_system_snapshot(
    az_commanded: float = 183.7, el_commanded: float = 52.4
) -> dict:
    t = time.time()

    alma_states = [
        sample_dish_state(dish, az_commanded, el_commanded, t) for dish in ALMA_ARRAY
    ]

    online_dishes = [d for d in alma_states if d["online"]]
    avg_tsys = (
        sum(d["tsys_k"] for d in online_dishes) / len(online_dishes)
        if online_dishes
        else 0
    )
    fault_count = sum(1 for d in alma_states if not d["online"])

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commanded_target": {
            "name": "Sgr A*",
            "az_deg": az_commanded,
            "el_deg": el_commanded,
            "ra": "17h 45m 40.04s",
            "dec": "-29° 00′ 28.1″",
        },
        "system": {
            "band": system_state.active_band,
            "freq_ghz": BAND_FREQ_GHZ.get(system_state.active_band, 0),
            "obs_mode": system_state.obs_mode,
            "fault_count": fault_count,
        },
        "alma": {
            "dishes": alma_states,
            "online_count": len(online_dishes),
            "total_count": len(ALMA_ARRAY),
            "avg_tsys_k": round(avg_tsys, 1),
        },
        "large_telescopes": LARGE_TELESCOPES,
        "atmosphere": sample_atmosphere(t),
    }
