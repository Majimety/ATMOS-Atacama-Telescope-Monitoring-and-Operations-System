"""
telescope.py — Pydantic models สำหรับ telescope state
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class DishStatus(BaseModel):
    id: str
    online: bool
    faulted: bool
    ant_type: str
    diameter_m: float
    az_deg: float
    el_deg: float
    tsys_k: Optional[float]
    signal_dbm: Optional[float]
    east_m: float
    north_m: float


class AtmosphereStatus(BaseModel):
    temp_c: float
    humidity_pct: float
    wind_ms: float
    wind_dir_deg: float
    pressure_hpa: float
    pwv_mm: float
    tau_225ghz: float
    seeing_arcsec: float
    source: str


class SystemStatus(BaseModel):
    band: int
    freq_ghz: float
    obs_mode: str
    target_name: str
    target_ra: str
    target_dec: str
    pointing_mode: str


class SystemSnapshot(BaseModel):
    timestamp: str
    system: SystemStatus
    atmosphere: AtmosphereStatus
    alma: dict
    pointing_mode: str
