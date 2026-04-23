"""
main.py — ATMOS FastAPI Application
"""
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ws.telemetry import telemetry_endpoint, pool
from app.scheduler import scheduler, ObservationJob, JobPriority
from app.simulation.alma_sim import cmd_inject_fault, cmd_set_band, cmd_set_mode
from app.simulation.pointing_sim import controller
from influx_writer import influx_writer
from auth import router as auth_router

app = FastAPI(title="ATMOS API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth routes ───────────────────────────────────────────────────────────────
app.include_router(auth_router)


# ── Health / status ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "online", "system": "ATMOS", "version": "0.3.0"}


@app.get("/health")
def health():
    az, el, mode = controller.step()
    return {
        "status": "ok",
        "pointing": {"az": az, "el": el, "mode": mode},
        "connections": pool.count,
        "influx": influx_writer.status(),
        "scheduler": {
            "queued": scheduler.get_state()["stats"]["queued"],
            "active": scheduler.get_state()["active"] is not None,
        },
    }


# ── REST control ──────────────────────────────────────────────────────────────

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
    priority: int = 2          # 0=urgent 1=high 2=normal 3=low
    notes: str = ""


@app.post("/api/scheduler/jobs")
async def add_job(req: AddJobRequest):
    job = ObservationJob(
        target_name=req.target_name,
        ra=req.ra, dec=req.dec,
        az=req.az, el=req.el,
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
async def remove_job(job_id: str):
    removed = await scheduler.remove_job(job_id)
    return {"ok": removed}


@app.post("/api/scheduler/jobs/{job_id}/move")
async def move_job(job_id: str, direction: int = 0):
    await scheduler.move_job(job_id, direction)
    return {"ok": True}


@app.post("/api/scheduler/skip")
async def skip_active():
    await scheduler.skip_active()
    return {"ok": True}


# ── InfluxDB status ───────────────────────────────────────────────────────────

@app.get("/api/influx/status")
def influx_status():
    return influx_writer.status()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await telemetry_endpoint(ws)
