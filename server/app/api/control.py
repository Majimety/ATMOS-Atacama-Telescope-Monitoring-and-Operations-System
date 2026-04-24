"""
control.py — REST control endpoints (slew, stow, band, mode, fault)
สำหรับ external tools / scripting / testing
การควบคุมปกติจาก Dashboard ผ่าน WebSocket /ws/telemetry
"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.simulation.alma_sim import (
    cmd_slew,
    cmd_stow,
    cmd_set_band,
    cmd_set_mode,
    cmd_inject_fault,
    cmd_clear_fault,
)
from app.simulation.pointing_sim import controller

router = APIRouter(prefix="/api/control", tags=["control"])


class SlewCommand(BaseModel):
    az: float
    el: float
    target_name: str = "Custom"


class FaultCommand(BaseModel):
    dish_id: str
    offline: bool


@router.post("/slew")
def slew(cmd: SlewCommand):
    cmd_slew(cmd.az, cmd.el, cmd.target_name)
    controller.command_slew(cmd.az, cmd.el)   # sync pointing_sim ด้วย
    return {"ok": True, "az": cmd.az, "el": cmd.el}


@router.post("/stow")
def stow():
    cmd_stow()
    controller.command_stow()                  # sync pointing_sim ด้วย
    return {"ok": True, "mode": "stow"}


@router.post("/band/{band}")
def set_band(band: int):
    if band not in range(1, 11):
        return {"error": "Band must be 1-10"}, 400
    cmd_set_band(band)
    return {"ok": True, "band": band}


@router.post("/mode/{mode}")
def set_mode(mode: str):
    valid_modes = {"interferometry", "single-dish", "vlbi", "commissioning", "maintenance"}
    if mode not in valid_modes:
        return {"error": f"Unknown mode. Valid: {valid_modes}"}, 400
    cmd_set_mode(mode)
    return {"ok": True, "mode": mode}


@router.post("/fault")
def inject_fault(cmd: FaultCommand):
    if cmd.offline:
        cmd_inject_fault(cmd.dish_id, True)
    else:
        cmd_clear_fault(cmd.dish_id)
    return {"ok": True, "dish_id": cmd.dish_id, "offline": cmd.offline}


@router.get("/pointing")
def get_pointing():
    az, el, mode = controller.step()
    return {"az": az, "el": el, "mode": mode}
