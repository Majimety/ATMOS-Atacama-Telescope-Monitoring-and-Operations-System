"""
server/app/api/scheduler.py — REST endpoints for the observation scheduler

All write operations (enqueue, remove, reorder, skip) require operator+ role.
Read access (GET state) is open to any authenticated user.

Routes:
  GET  /api/scheduler                  — queue state + active job + history
  POST /api/scheduler/jobs             — enqueue a new observation job  (operator+)
  DEL  /api/scheduler/jobs/{id}        — remove a queued job            (operator+)
  POST /api/scheduler/jobs/{id}/move   — reorder up/down                (operator+)
  POST /api/scheduler/skip             — skip the active job            (operator+)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.obs_queue import scheduler, ObservationJob, JobPriority
from auth import require_role, Role, User

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


# ── Request models ────────────────────────────────────────────────────────────


class JobRequest(BaseModel):
    target_name: str
    ra: str
    dec: str
    az: float
    el: float
    band: int = Field(ge=1, le=10)
    duration_s: int = Field(gt=0)
    min_el_deg: float = 15.0
    max_pwv_mm: float = 3.0
    priority: str = "normal"
    notes: str = ""


class MoveRequest(BaseModel):
    direction: int = Field(..., description="-1 = move up, +1 = move down")


_PRIORITY_MAP = {
    "urgent": JobPriority.URGENT,
    "high": JobPriority.HIGH,
    "normal": JobPriority.NORMAL,
    "low": JobPriority.LOW,
}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def get_scheduler_state():
    """Return current queue, active job, history, and stats.
    Readable by any authenticated role."""
    return scheduler.get_state()


@router.post("/jobs", status_code=201)
async def enqueue_job(
    body: JobRequest,
    user: User = Depends(require_role(Role.OPERATOR)),
):
    """Enqueue a new observation job. Requires operator+."""
    job = ObservationJob(
        target_name=body.target_name,
        ra=body.ra,
        dec=body.dec,
        az=body.az,
        el=body.el,
        band=body.band,
        duration_s=body.duration_s,
        min_el_deg=body.min_el_deg,
        max_pwv_mm=body.max_pwv_mm,
        priority=_PRIORITY_MAP.get(body.priority.lower(), JobPriority.NORMAL),
        notes=body.notes,
    )
    await scheduler.add_job(job)
    return {"status": "queued", "job_id": job.job_id}


@router.delete("/jobs/{job_id}")
async def remove_job(
    job_id: str,
    user: User = Depends(require_role(Role.OPERATOR)),
):
    """Remove a queued job by ID. Requires operator+."""
    removed = await scheduler.remove_job(job_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"Job '{job_id}' not found in queue"
        )
    return {"status": "removed", "job_id": job_id}


@router.post("/jobs/{job_id}/move")
async def move_job(
    job_id: str,
    body: MoveRequest,
    user: User = Depends(require_role(Role.OPERATOR)),
):
    """Reorder a queued job up (-1) or down (+1). Requires operator+."""
    await scheduler.move_job(job_id, body.direction)
    return {"status": "moved", "job_id": job_id, "direction": body.direction}


@router.post("/skip")
async def skip_active_job(
    user: User = Depends(require_role(Role.OPERATOR)),
):
    """Skip (abort) the currently running job. Requires operator+."""
    if scheduler._active is None:
        raise HTTPException(status_code=404, detail="No active job to skip")
    await scheduler.skip_active()
    return {"status": "skipped"}
