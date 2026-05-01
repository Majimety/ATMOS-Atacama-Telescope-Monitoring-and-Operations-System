"""
main.py — ATMOS FastAPI Application
"""

import os

from fastapi import FastAPI, WebSocket, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ws.telemetry import telemetry_endpoint, pool
from server.app.obs_queue import scheduler, ObservationJob, JobPriority
from app.simulation.alma_sim import cmd_inject_fault, cmd_set_band, cmd_set_mode
from app.simulation.pointing_sim import controller
from app.api import atmosphere, telescopes, control as control_api
from influx_writer import influx_writer
from auth import router as auth_router, ws_authenticate, Role, require_role, User

app = FastAPI(title="ATMOS API", version="0.3.1")

# ── CORS — อ่านจาก env, fallback dev origins ─────────────────────────────────
_raw_origins = os.getenv(
    "ATMOS_CORS_ORIGINS", "http://localhost:5173,http://localhost:80"
)
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(control_api.router)
app.include_router(atmosphere.router)
app.include_router(telescopes.router)


# ── Health / status ───────────────────────────────────────────────────────────


@app.get("/")
def root():
    return {"status": "online", "system": "ATMOS", "version": "0.3.1"}


@app.get("/health")
def health():
    az, el, mode = controller.step()
    return {
        "status": "ok",
        "pointing": {"az": az, "el": el, "mode": mode},
        "connections": pool.count,
        "influx": influx_writer.status(),
        "cors_origins": CORS_ORIGINS,
        "scheduler": {
            "queued": scheduler.get_state()["stats"]["queued"],
            "active": scheduler.get_state()["active"] is not None,
        },
    }


# ── REST control (legacy inline — delegate to control_api) ────────────────────
# Kept for backward-compatibility; control_api.router handles /api/control/*


class SlewCommand(BaseModel):
    az: float
    el: float


class FaultCommand(BaseModel):
    dish_id: str
    offline: bool


@app.post("/api/slew")
def api_slew(cmd: SlewCommand):
    controller.command_slew(cmd.az, cmd.el)
    return {"ok": True}


@app.post("/api/stow")
def api_stow():
    controller.command_stow()
    return {"ok": True}


@app.post("/api/band/{band}")
def api_set_band(band: int):
    cmd_set_band(band)
    return {"ok": True, "band": band}


@app.post("/api/mode/{mode}")
def api_set_mode(mode: str):
    cmd_set_mode(mode)
    return {"ok": True, "mode": mode}


@app.post("/api/fault")
def api_inject_fault(cmd: FaultCommand):
    cmd_inject_fault(cmd.dish_id, cmd.offline)
    return {"ok": True}


# ── Scheduler REST API ────────────────────────────────────────────────────────


@app.get("/api/scheduler")
def get_scheduler():
    return scheduler.get_state()


class AddJobRequest(BaseModel):
    target_name: str
    ra: str = ""
    dec: str = ""
    az: float = 0.0
    el: float = 45.0
    band: int = 6
    duration_s: int = 3600
    min_el_deg: float = 15.0
    max_pwv_mm: float = 3.0
    priority: int = 2  # 0=urgent 1=high 2=normal 3=low
    notes: str = ""


@app.post("/api/scheduler/jobs")
async def add_job(
    req: AddJobRequest,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    job = ObservationJob(
        target_name=req.target_name,
        ra=req.ra,
        dec=req.dec,
        az=req.az,
        el=req.el,
        band=req.band,
        duration_s=req.duration_s,
        min_el_deg=req.min_el_deg,
        max_pwv_mm=req.max_pwv_mm,
        priority=JobPriority(req.priority),
        notes=req.notes,
    )
    await scheduler.add_job(job)
    return {"ok": True, "job_id": job.job_id}


@app.delete("/api/scheduler/jobs/{job_id}")
async def remove_job(
    job_id: str,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    removed = await scheduler.remove_job(job_id)
    return {"ok": removed}


@app.post("/api/scheduler/jobs/{job_id}/move")
async def move_job(
    job_id: str,
    direction: int = 0,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    await scheduler.move_job(job_id, direction)
    return {"ok": True}


@app.post("/api/scheduler/skip")
async def skip_active(
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    await scheduler.skip_active()
    return {"ok": True}


# ── InfluxDB status ───────────────────────────────────────────────────────────


@app.get("/api/influx/status")
def influx_status():
    return influx_writer.status()


# ── WebSocket — ต้องผ่าน auth (token query param) ─────────────────────────────


@app.websocket("/ws/telemetry")
async def ws_telemetry(
    ws: WebSocket,
    token: str = Query(default=""),
):
    """
    WebSocket telemetry stream.
    ถ้า token ว่าง → รับ connection ในฐานะ viewer (demo/dev mode)
    ถ้า token ไม่ valid → FastAPI ส่ง close frame 4403 กลับอัตโนมัติ

    Authentication ทำที่นี่เพียงจุดเดียว — telemetry_endpoint()
    ไม่เรียก ws_authenticate() ซ้ำอีก (FIX Bug 1)
    """
    if token:
        await ws_authenticate(
            token, Role.VIEWER
        )  # raise WebSocketException(4403) ถ้า invalid

    await telemetry_endpoint(ws)
