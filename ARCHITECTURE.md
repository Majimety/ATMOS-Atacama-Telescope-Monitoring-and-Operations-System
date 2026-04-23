# ATMOS — Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        BROWSER                              │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  3D Scene   │  │  Dashboard   │  │   Control Panel   │   │
│  │  (Three.js) │  │  (Zustand)   │  │   (WebSocket TX)  │   │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬────────┘   │
│         │                │                     │            │
│  ┌──────▼────────────────▼─────────────────────▼─────────┐  │
│  │             useTelemetryStore (Zustand)               │  │
│  │             useAlertStore (Zustand)                   │  │
│  │             useTelescopeStore (Zustand)               │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │           useWebSocket / resilientWS.js               │  │
│  │         (reconnect, buffer, gap detection)            │  │
│  └──────────────────────────┬────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │ WebSocket (JSON, 1Hz)
                              │ ws://localhost:8000/ws/telemetry
┌─────────────────────────────┼───────────────────────────────┐
│                        FASTAPI SERVER                       │
│                             │                               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │              app/ws/telemetry.py                      │  │
│  │           ConnectionPool (broadcast to N clients)     │  │
│  └──────────────────────────┬────────────────────────────┘  │
│                             │                               │
│  ┌──────────────────────────▼────────────────────────────┐  │
│  │           app/simulation/alma_sim.py                  │  │
│  │     get_system_snapshot() — builds full JSON frame    │  │
│  └────┬────────────┬───────────────┬─────────────────────┘  │
│       │            │               │                        │
│  ┌────▼────┐  ┌────▼────┐  ┌───────▼──────┐                 │
│  │physics  │  │pointing │  │weather_fetch │ ← Open-Meteo    │
│  │_models  │  │_sim.py  │  │er.py (async) │   (real data)   │
│  └─────────┘  └─────────┘  └──────────────┘                 │
│                                                             │
│  REST API:                                                  │
│    GET  /api/telescopes/      — list all dishes             │
│    GET  /api/atmosphere/      — current met data            │
│    POST /api/control/slew     — point to az/el              │
│    POST /api/control/band/6   — set receiver band           │
│    POST /api/control/fault    — inject/clear fault          │
│    GET  /api/scheduler        — queue state + history       │
│    POST /api/scheduler/jobs   — enqueue observation job     │
│    DEL  /api/scheduler/jobs/{id} — remove job (operator+)   │
│    POST /api/scheduler/skip   — skip active job (operator+) │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Weather** — `weather_fetcher.py` polls Open-Meteo every 5 min
   - If live data available: uses real Chajnantor temp/humidity/wind/pressure
   - Derives PWV from Clausius-Clapeyron equation
   - Derives τ₂₂₅GHz from PWV (Pardo et al. 2001 ATM model)
   - Fallback: `atmosphere_sim.py` generates realistic simulation

2. **Physics** — `physics_models.py` computes per-dish values
   - Tsys = f(T_rx, τ_band, airmass) — ALMA Technical Handbook Eq. 9.8
   - τ_band = τ_scale[band] × τ₂₂₅GHz
   - airmass = Kasten-Young (1989) formula

3. **Pointing** — `pointing_sim.py` simulates slew motion
   - ALMA slew rate: 2°/s az, 1°/s el
   - Smooth interpolation toward commanded az/el
   - Stow position: az=0°, el=15°

4. **Snapshot** — `alma_sim.get_system_snapshot()` assembles full frame
   - ~50 dishes × {az, el, tsys, signal, online} + atmosphere + system state
   - Broadcast over WebSocket every 1 second

## Scheduler

```
REST /api/scheduler/*
  └── ObservationScheduler (asyncio, 1s tick)
        ├── evaluate_constraints()
        │     elevation > min_el_deg
        │     AND PWV < max_pwv_mm
        │     AND wind < critical threshold
        ├── start_job()    begins observation, streams progress via WS
        └── complete_job() moves to history (last 20 entries)

ObservationJob fields:
  id, target, ra, dec, band, duration_s,
  min_el_deg, max_pwv_mm, priority (urgent/high/normal/low)

Pre-seeded targets: Sgr A*, M87, Orion KL, 3C 273, Crab Nebula
Queue operations:   enqueue, reorder (▲▼), remove ✕ (operator+ only)
```

## Auth Flow

```
POST /api/auth/login
  ├── backend available  → validate credentials → JWT
  │                        (expiry: ATMOS_ACCESS_TOKEN_EXPIRE_MINUTES)
  └── backend unreachable → demo mode local validation
                            (no python-jose required on client)

Roles (descending access):
  admin > engineer > operator > observer

UI gate:
  LoginPage.jsx renders before Dashboard
  → on success: role badge + username + LOGOUT button in App.jsx header
  → SCHED tab available in right panel for all authenticated roles
  → scheduler write operations (reorder/remove/skip) gated to operator+

Demo accounts (local fallback):
  admin    / admin123
  operator / op123
  observer / obs123
```

## InfluxDB Write Path

```
telemetry tick (1 Hz)
  └── influx_writer.write()
        ├── buffer < 50 points AND < 10 s elapsed → hold
        └── flush condition met → write to InfluxDB
              ├── dish_telemetry   per-dish: az, el, tsys, signal, online
              ├── array_summary    online_count, avg_tsys
              └── atmosphere       pwv_mm, tau_225ghz, wind_ms, temp_c
        error → suppress + log WARNING (telemetry loop unaffected)

Startup behaviour:
  INFLUX_TOKEN unset → writer auto-disabled (lazy init, no import crash)
  INFLUX_TOKEN set   → persistent async client initialised on first write
```

## File Structure

```
server/
  main.py                      FastAPI app + REST routes
  auth.py                      JWT + RBAC (4 roles)
  influx_writer.py             InfluxDB batch writer (lazy init, auto-disable)
  requirements.txt
  app/
    scheduler.py               ObservationJob dataclass + ObservationScheduler engine
    models/
      telescope.py             Pydantic data models
      telemetry.py             ConnectionPool (legacy, see ws/)
    simulation/
      alma_sim.py              Main simulation engine
      alma_positions.py        Real ALMA C43-5 pad coordinates
      physics_models.py        Tsys, airmass, signal calculations
      pointing_sim.py          Slew/track motion controller
      atmosphere_sim.py        Fallback atmospheric simulation
      weather_fetcher.py       Open-Meteo API client
    ws/
      telemetry.py             WebSocket endpoint + command handler + scheduler/influx wiring
      events.py                Event type constants
    api/
      telescopes.py            REST: dish listing
      atmosphere.py            REST: met data
      control.py               REST: slew/stow/band/fault
      scheduler.py             REST: job CRUD + skip

client/src/
  App.jsx                      Root component + login gate + role badge + SCHED tab
  main.jsx                     React entry point
  hooks/
    useWebSocket.js            Basic WebSocket hook
    useTelemetry.js            Snapshot → store → alerts pipeline
  store/
    telemetryStore.js          Zustand: snapshot + history
    alertStore.js              Zustand: alert queue
    alertEngine.js             Rule-based alert detection
    telescopeStore.js          Zustand: selection + filter state
    auth.js                    Auth state (JWT, role) + demo mode local fallback
  components/
    Dashboard.jsx              System status overview
    TelescopePanel.jsx         Scrollable dish list
    ControlPanel.jsx           Slew/stow/band/mode controls
    TelemetryGraphs.jsx        Live sparkline graphs
    AlertFeed.jsx              Event log
    SchedulerPanel.jsx         Observation queue + progress bar + history log
    UVCoveragePlot.jsx         UV-plane coverage (science)
    BaselineCorrelator.jsx     Baseline correlation matrix (science)
  three/
    Scene.jsx                  Three.js canvas + all 3D objects
    DishMesh.jsx               Single dish 3D model
    SkyDome.jsx                Night sky + stars
    TerrainMesh.jsx            Atacama plateau terrain
  pages/
    LoginPage.jsx              Terminal-aesthetic auth screen (CRT scanlines, amber prompt)
    Config.jsx                 Settings page
  libs/
    resilientWS.js             Production WebSocket (backoff, buffer)

docker/
  docker-compose.yml           Full production stack
  Dockerfile.server            FastAPI container
  Dockerfile.client            Nginx + React build

influx/
  schema.flux                  InfluxDB Flux query examples
  seed.py                      Seed 24h of historical data
```