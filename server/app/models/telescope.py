"""
telescopes.py — REST endpoints สำหรับอ่าน telescope state
"""

from fastapi import APIRouter, HTTPException
from app.simulation.alma_sim import ANTENNA_ARRAY, _system_state, _injected_faults

router = APIRouter(prefix="/api/telescopes", tags=["telescopes"])


@router.get("/")
def list_telescopes():
    return {
        "count": len(ANTENNA_ARRAY),
        "telescopes": [
            {
                "id": ant["id"],
                "type": ant["ant_type"],
                "east_m": ant["east_m"],
                "north_m": ant["north_m"],
                "diameter_m": ant["diameter_m"],
                "baseline_online": ant["online"],
            }
            for ant in ANTENNA_ARRAY
        ],
    }


@router.get("/system/state")
def get_system_state():
    return _system_state


@router.get("/{dish_id}")
def get_telescope(dish_id: str):
    for ant in ANTENNA_ARRAY:
        if ant["id"] == dish_id:
            return {
                **ant,
                "faulted_injected": dish_id in _injected_faults,
            }
    raise HTTPException(status_code=404, detail=f"Dish {dish_id!r} not found")
