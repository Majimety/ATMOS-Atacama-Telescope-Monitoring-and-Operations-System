"""
main.py — ATMOS FastAPI Application
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ws.telemetry import telemetry_endpoint, pool
from app.obs_queue import scheduler, ObservationJob, JobPriority
from app.simulation.alma_sim import cmd_inject_fault, cmd_set_band, cmd_set_mode
from app.simulation.pointing_sim import controller
from app.api import atmosphere, telescopes, control as control_api
from app.api import scheduler as scheduler_api
from influx_writer import influx_writer
from auth import router as auth_router, ws_authenticate, Role, require_role, User

# ── Lifespan (INF-02): เรียก influx_writer.close() ตอน shutdown ──────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan — flush InfluxDB buffer ก่อน shutdown"""
    yield
    await influx_writer.close()


app = FastAPI(title="ATMOS API", version="0.3.0", lifespan=lifespan)

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

app.include_router(auth_router)
app.include_router(control_api.router)
app.include_router(atmosphere.router)
app.include_router(telescopes.router)
app.include_router(scheduler_api.router)


@app.get("/")
def root():
    return {"status": "online", "system": "ATMOS", "version": "0.3.0"}


# PTG-02: /health ต้องไม่เรียก controller.step() ซึ่งมี side effect
# ใช้ current_az/current_el/mode โดยตรงแทน
@app.get("/health")
def health():
    return {
        "status": "ok",
        "pointing": {
            "az": round(controller.current_az, 3),
            "el": round(controller.current_el, 3),
            "mode": controller.mode,
        },
        "connections": pool.count,
        "influx": influx_writer.status(),
        "cors_origins": CORS_ORIGINS,
        "scheduler": {
            "queued": scheduler.get_state()["stats"]["queued"],
            "active": scheduler.get_state()["active"] is not None,
        },
    }


class SlewCommand(BaseModel):
    az: float
    el: float


class FaultCommand(BaseModel):
    dish_id: str
    offline: bool


# API-04: legacy endpoints ต้องมี auth guard ──────────────────────────────────


@app.post("/api/slew")
def api_slew(
    cmd: SlewCommand,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    """Legacy slew endpoint — requires operator+."""
    controller.command_slew(cmd.az, cmd.el)
    return {"ok": True}


@app.post("/api/stow")
def api_stow(
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    """Legacy stow endpoint — requires operator+."""
    controller.command_stow()
    return {"ok": True}


@app.post("/api/band/{band}")
def api_set_band(
    band: int,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    """Legacy band endpoint — requires operator+."""
    cmd_set_band(band)
    return {"ok": True, "band": band}


@app.post("/api/mode/{mode}")
def api_set_mode(
    mode: str,
    _user: User = Depends(require_role(Role.OPERATOR)),
):
    """Legacy mode endpoint — requires operator+."""
    cmd_set_mode(mode)
    return {"ok": True, "mode": mode}


@app.post("/api/fault")
def api_inject_fault(
    cmd: FaultCommand,
    _user: User = Depends(require_role(Role.ENGINEER)),
):
    """Legacy fault endpoint — requires engineer+."""
    cmd_inject_fault(cmd.dish_id, cmd.offline)
    return {"ok": True}


@app.get("/api/influx/status")
def influx_status():
    return influx_writer.status()


@app.websocket("/ws/telemetry")
async def ws_telemetry(
    ws: WebSocket,
    token: str = Query(default=""),
):
    if token:
        await ws_authenticate(token, Role.VIEWER)

    await telemetry_endpoint(ws)
