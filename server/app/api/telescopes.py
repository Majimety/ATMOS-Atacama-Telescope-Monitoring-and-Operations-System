"""
telescopes.py — REST endpoints สำหรับอ่าน telescope state
"""
from fastapi import APIRouter
from app.simulation.alma_sim import ANTENNA_ARRAY, _system_state, _injected_faults

router = APIRouter(prefix="/api/telescopes", tags=["telescopes"])


@router.get("/")
def list_telescopes():
    """คืน array ของ telescope ทั้งหมดพร้อม static metadata"""
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


@router.get("/{dish_id}")
def get_telescope(dish_id: str):
    """คืน metadata ของ dish หนึ่งตัว"""
    for ant in ANTENNA_ARRAY:
        if ant["id"] == dish_id:
            return {
                **ant,
                "faulted_injected": dish_id in _injected_faults,
            }
    return {"error": f"Dish {dish_id!r} not found"}, 404


@router.get("/system/state")
def get_system_state():
    """คืน system-level state (band, mode, target)"""
    return _system_state
