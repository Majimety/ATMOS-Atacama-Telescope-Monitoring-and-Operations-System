"""
events.py — WebSocket event type definitions สำหรับ ATMOS

ทุก message ระหว่าง Frontend ↔ Backend ใช้ format:
  { "type": "<event_type>", ...payload }

Client → Server (commands):
  slew          { az, el, target_name? }
  stow          {}
  set_band      { band: 1-10 }
  set_mode      { mode: string }
  inject_fault  { dish_id, offline: bool }
  ping          {}

Server → Client (telemetry stream):
  telemetry     full SystemSnapshot object (1Hz)
  pong          { ts: float }  — response to ping
  error         { message: string }
"""

# Event type constants — ใช้ทั้งใน Python backend และ document ให้ JS frontend
TELEMETRY   = "telemetry"
SLEW        = "slew"
STOW        = "stow"
SET_BAND    = "set_band"
SET_MODE    = "set_mode"
INJECT_FAULT = "inject_fault"
CLEAR_FAULT = "clear_fault"
PING        = "ping"
PONG        = "pong"
ERROR       = "error"

ALL_CLIENT_COMMANDS = {SLEW, STOW, SET_BAND, SET_MODE, INJECT_FAULT, CLEAR_FAULT, PING}
ALL_SERVER_EVENTS   = {TELEMETRY, PONG, ERROR}
