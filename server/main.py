"""
main.py — ATMOS FastAPI Application
"""

import os

from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ws.telemetry import telemetry_endpoint, pool
from app.scheduler import scheduler, ObservationJob, JobPriority
from app.simulation.alma_sim import cmd_inject_fault, cmd_set_band, cmd_set_mode
from app.simulation.pointing_sim import controller
from app.api import atmosphere, telescopes, control as control_api
from app.api.scheduler import router as scheduler_router
from influx_writer import influx_writer
from auth import router as auth_router, ws_authenticate, Role

app = FastAPI(title="ATMOS API", version="0.3.0")

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
app.include_router(scheduler_router)

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


# ── InfluxDB status ───────────────────────────────────────────────────────────


@app.get("/api/influx/status")
def influx_status():
    return influx_writer.status()


# ── WebSocket — ต้องผ่าน auth (token query param) ─────────────────────────────


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket, token: str = Query(default="")):
    await ws_authenticate(token, Role.VIEWER)  # ← บังคับทุก connection
    await telemetry_endpoint(ws, token)
