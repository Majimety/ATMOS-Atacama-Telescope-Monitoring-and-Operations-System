from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ws.telemetry import telemetry_endpoint
from app.simulation.alma_sim import (
    cmd_inject_fault,
    cmd_set_band,
    cmd_set_mode,
)
from app.simulation.pointing_sim import controller


app = FastAPI(title="ATMOS API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "online", "system": "ATMOS", "version": "0.2.0"}


@app.get("/health")
def health():
    az, el, mode = controller.step()
    return {"status": "ok", "pointing": {"az": az, "el": el, "mode": mode}}


# ── REST endpoints ────────────────────────────────────────────────────────────
# สำหรับ external tools / testing / scripting เท่านั้น
# การควบคุมปกติจาก Dashboard ผ่าน WebSocket /ws/telemetry


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


# ── WebSocket ─────────────────────────────────────────────────────────────────


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await telemetry_endpoint(ws)
