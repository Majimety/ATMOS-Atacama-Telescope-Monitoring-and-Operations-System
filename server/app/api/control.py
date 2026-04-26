"""
control.py — Authenticated REST control endpoints for ATMOS
============================================================

These endpoints provide an HTTP interface to the telescope control functions
for use by external scripts, CI pipelines, and integration tests.  Normal
dashboard operation uses the WebSocket command channel instead.

Access control
--------------
All mutating endpoints require at least the ``OPERATOR`` role.  The fault
injection endpoint requires the ``ENGINEER`` role because injecting faults
affects array health reporting and should be restricted to personnel who
understand the implications.  The read-only ``/pointing`` endpoint is
accessible to all authenticated users (``VIEWER`` and above).

Role enforcement is implemented via FastAPI ``Depends`` on the
``require_role`` factory from ``auth.py``.  Unauthenticated requests receive
HTTP 401; requests with insufficient role receive HTTP 403.
"""

from fastapi import APIRouter, Depends
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
from auth import require_role, Role, User

router = APIRouter(prefix="/api/control", tags=["control"])


# ── Request models ────────────────────────────────────────────────────────────


class SlewCommand(BaseModel):
    az: float
    el: float
    target_name: str = "Custom"


class FaultCommand(BaseModel):
    dish_id: str
    offline: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/slew")
def slew(
    cmd: SlewCommand,
    _user: User = Depends(require_role(Role.OPERATOR)),
) -> dict:
    """
    Command all antennas to slew to the specified azimuth and elevation.

    Updates both the ALMA simulation state and the pointing controller so
    that the 3-D viewport and telemetry stream reflect the new target
    immediately.
    """
    cmd_slew(cmd.az, cmd.el, cmd.target_name)
    controller.command_slew(cmd.az, cmd.el)
    return {"ok": True, "az": cmd.az, "el": cmd.el}


@router.post("/stow")
def stow(
    _user: User = Depends(require_role(Role.OPERATOR)),
) -> dict:
    """
    Command all antennas to move to the stow position.

    The stow position points the dish face directly upward, minimising wind
    load and protecting the receiver cabin during high-wind or maintenance
    conditions.
    """
    cmd_stow()
    controller.command_stow()
    return {"ok": True, "mode": "stow"}


@router.post("/band/{band}")
def set_band(
    band: int,
    _user: User = Depends(require_role(Role.OPERATOR)),
) -> dict:
    """
    Switch the array to the specified receiver band (1–10).

    Band changes affect the simulated system temperature (Tsys), frequency
    label, and baseline correlation weights in the UV-coverage display.
    """
    if band not in range(1, 11):
        return {"error": "Band must be between 1 and 10 inclusive"}
    cmd_set_band(band)
    return {"ok": True, "band": band}


@router.post("/mode/{mode}")
def set_mode(
    mode: str,
    _user: User = Depends(require_role(Role.OPERATOR)),
) -> dict:
    """
    Set the array observation mode.

    Valid modes: ``interferometry``, ``single-dish``, ``vlbi``,
    ``commissioning``, ``maintenance``.  The mode label is broadcast in every
    telemetry frame and displayed in the dashboard header.
    """
    valid_modes = {
        "interferometry",
        "single-dish",
        "vlbi",
        "commissioning",
        "maintenance",
    }
    if mode not in valid_modes:
        return {"error": f"Unknown mode. Valid options: {sorted(valid_modes)}"}
    cmd_set_mode(mode)
    return {"ok": True, "mode": mode}


@router.post("/fault")
def inject_fault(
    cmd: FaultCommand,
    _user: User = Depends(require_role(Role.ENGINEER)),
) -> dict:
    """
    Inject or clear a hardware fault on a specific antenna.

    Setting ``offline=True`` marks the antenna as offline in the simulation,
    reducing ``online_count`` and excluding the dish from array health metrics
    and UV-coverage plots.  Setting ``offline=False`` restores the antenna to
    operational status.

    Requires the ``ENGINEER`` role because fault injection alters array health
    state visible to all users and should only be performed by qualified
    personnel.
    """
    if cmd.offline:
        cmd_inject_fault(cmd.dish_id, True)
    else:
        cmd_clear_fault(cmd.dish_id)
    return {"ok": True, "dish_id": cmd.dish_id, "offline": cmd.offline}


@router.get("/pointing")
def get_pointing(
    _user: User = Depends(require_role(Role.VIEWER)),
) -> dict:
    """
    Return the current pointing controller state (azimuth, elevation, mode).

    Read-only endpoint; accessible to all authenticated roles.
    """
    az, el, mode = controller.step()
    return {"az": az, "el": el, "mode": mode}
