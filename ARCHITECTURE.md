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
                              │ ⚠ NO AUTH — JWT validation not yet extended
                              │   to this endpoint (see Auth Flow § Known Gaps)
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
│    DEL  /api/scheduler/jobs/{id} — remove job (operator+) ⚠ role guard may be incomplete   │
│    POST /api/scheduler/skip   — skip active job (operator+) ⚠ role guard may be incomplete │
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
    BaselineCorrelator.jsx     Baseline correlation matrix (science) ⚠ uses simulateVisibilities() — not yet wired to live backend data
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
  seed.py                      Seed 24h of historical data ⚠ may generate stale schema if frame fields have changed
```

## Known Gaps & Roadmap Items

Items marked ⚠ are partially implemented; items marked ✗ are not yet implemented.

### Security
- ✗ **WebSocket auth** — `/ws/telemetry` is currently an open endpoint. JWT validation exists in `auth.py` and covers all REST routes, but has not yet been extended to the WebSocket handshake. Any client can connect and receive telemetry or send commands without a token.
- ⚠ **RBAC on scheduler write operations** — `DELETE /api/scheduler/jobs/{id}` and `POST /api/scheduler/skip` are documented as `operator+` only, but role enforcement in `app/api/scheduler.py` may be incomplete or absent.

### Data / Science
- ✗ **BaselineCorrelator live data** — `BaselineCorrelator.jsx` currently calls `simulateVisibilities()` (mock/synthetic data). It is not yet connected to a real visibility data feed from the backend.
- ⚠ **influx/seed.py schema drift** — `seed.py` seeds 24 hours of historical telemetry. If the WebSocket frame schema has gained new fields (e.g. `scheduler`), seeded data will be missing those fields and may cause type mismatches in Flux queries or Grafana panels.

### Tooling
- ⚠ **Vite version** — README specifies Vite 8.x, which has not yet been released (current stable: 6.x). Verify whether this is a typo or an intentional alpha/RC dependency before production builds.

---

## WebSocket Message Schema

Every telemetry tick the server serialises one JSON frame and broadcasts it to all connected clients. The top-level keys are stable; inner dish keys are dish IDs.

```jsonc
// Inbound frame — server → client (1 Hz)
{
  "type": "telemetry",
  "timestamp": "2025-05-03T14:22:01.004Z",   // ISO-8601 UTC

  "dishes": {
    "DA-01": {
      "az": 123.4,          // degrees, 0–360
      "el": 45.0,           // degrees, 0–90
      "tsys": 67.2,         // K — system noise temperature
      "signal": 0.84,       // 0.0–1.0 normalised signal level
      "online": true,       // false = dish offline or in fault
      "slewing": false,     // true while interpolating toward commanded az/el
      "band": 6,            // ALMA receiver band (1–10)
      "fault": null         // null | "DRIVE_ERROR" | "DEWAR_WARM" | ...
    }
    // ... DA-02 through DA-60, DV-01 through DV-06,
    //     "apex", "iram", "aste", "nanten2", "eht_alpha", "eht_beta"
  },

  "atmosphere": {
    "pwv_mm": 1.2,          // precipitable water vapour, mm
    "tau_225ghz": 0.048,    // zenith opacity at 225 GHz
    "wind_ms": 4.1,         // wind speed, m/s
    "wind_dir_deg": 217.0,  // wind direction, degrees
    "temp_c": -5.3,         // ambient temperature, °C
    "pressure_hpa": 556.0,  // atmospheric pressure, hPa
    "source": "open-meteo"  // "open-meteo" | "simulation"
  },

  "scheduler": {
    "active_job": {
      "id": "job-004",
      "target": "Sgr A*",
      "ra": 266.417,        // degrees J2000
      "dec": -29.008,
      "band": 6,
      "duration_s": 3600,
      "elapsed_s": 842,
      "priority": "urgent"  // urgent | high | normal | low
    },                      // null if no job running
    "queue": [
      { "id": "job-005", "target": "M87", "band": 3, "priority": "high" }
    ],
    "history": [
      { "id": "job-003", "target": "Orion KL", "completed_at": "2025-05-03T13:00:00Z", "status": "done" }
    ]
  },

  "system": {
    "online_count": 62,     // dishes currently online
    "total_count": 66,      // total ALMA dishes in simulation
    "avg_tsys": 71.4,       // array-wide mean Tsys, K
    "alert_count": 2        // active unacknowledged alerts
  }
}
```

Clients that only need a subset (e.g. the 3D scene reads only `dishes.*.az/el/online`) should destructure from the Zustand store rather than parsing the raw frame.

---

## WebSocket Command Schema

Commands are sent **client → server** over the same WebSocket connection as JSON objects. The server dispatches on `"cmd"`.

```jsonc
// Slew a dish to az/el
{ "cmd": "slew", "dish_id": "DA-01", "az": 180.0, "el": 60.0 }

// Stow a dish (moves to az=0°, el=15°)
{ "cmd": "stow", "dish_id": "DA-01" }

// Stow all dishes simultaneously
{ "cmd": "stow_all" }

// Change receiver band (1–10)
{ "cmd": "set_band", "dish_id": "DA-01", "band": 7 }

// Inject a fault (triggers alert + marks dish offline)
{ "cmd": "fault_inject", "dish_id": "DA-01", "fault": "DRIVE_ERROR" }

// Clear an injected fault (returns dish to online)
{ "cmd": "fault_clear", "dish_id": "DA-01" }
```

> **Auth gap** — the command handler in `app/ws/telemetry.py` currently processes all commands without checking the sender's JWT or role. Until WebSocket auth is implemented, any anonymous client can issue stow/fault commands.

---

## Frontend Data Pipeline

The pipeline from raw wire bytes to rendered pixels has four sequential stages:

```
WebSocket frame (JSON string)
  │
  ▼
resilientWS.js / useWebSocket.js
  │  onmessage → JSON.parse() → calls registered handler
  │
  ▼
useTelemetry.js   (the pipeline hub)
  │  1. Writes raw snapshot into telemetryStore   (full frame + rolling history)
  │  2. Passes snapshot to alertEngine.js
  │  3. Writes any new alerts into alertStore
  │
  ├──▶ telemetryStore (Zustand)
  │      snapshot        — latest full frame, replaced every tick
  │      history[300]    — ring buffer, 300 s ≈ 5 min of sparkline data
  │
  ├──▶ alertStore (Zustand)
  │      alerts[]        — ordered queue, newest first
  │      acknowledge(id) — marks alert read, does not remove
  │
  └──▶ telescopeStore (Zustand)
         selected        — currently focused dish ID
         filter          — "all" | "online" | "offline" | "fault"
         (read-only view of telemetryStore data, no writes from pipeline)
  │
  ▼
React components subscribe via Zustand selectors
  │  Components only re-render when their specific slice changes.
  │  Three.js Scene.jsx reads dishes via useFrame() loop — bypasses
  │  React reconciler entirely for 60 fps 3D updates.
  │
  ▼
Rendered UI
```

### Alert Engine Rules (`alertEngine.js`)

The engine runs once per telemetry tick synchronously inside `useTelemetry.js`. It compares the incoming snapshot against fixed thresholds and emits alert objects for any new violations:

| Rule | Condition | Severity |
|------|-----------|----------|
| Dish offline | `dish.online === false` | warning |
| Tsys threshold | `dish.tsys > 150 K` | warning |
| Tsys critical | `dish.tsys > 250 K` | critical |
| Wind warning | `atmosphere.wind_ms > 12` | warning |
| Wind critical | `atmosphere.wind_ms > 20` | critical |
| PWV elevated | `atmosphere.pwv_mm > 3.0` | warning |
| PWV critical | `atmosphere.pwv_mm > 6.0` | critical |

Alerts are deduplicated by `dish_id + rule` — a dish that stays offline does not flood the queue with repeated entries.

### WebSocket Hook Duality

Two WebSocket hooks coexist:

| Hook | Location | Purpose |
|------|----------|---------|
| `useWebSocket.js` | `hooks/` | Thin hook, used in development and simple consumers. No retry logic. |
| `resilientWS.js` | `libs/` | Production client. Exponential backoff (initial 500 ms, max 30 s, jitter ±20%), message buffer held during reconnect and flushed on reconnection, gap detection via timestamp diff. |

`useTelemetry.js` should use `resilientWS.js` in production builds. If both are active simultaneously they will create duplicate connections — verify the import in `useTelemetry.js` before deploying.

---

## Coordinate System & Telescope Layout

### ALMA Pad Coordinates (`alma_positions.py`)

Pad positions are sourced from the real ALMA C43-5 configuration (CASA `simobserve` pad file). The coordinate frame is **local topocentric East-North-Up (ENU)** referenced to the ALMA Array Operations Site (AOS) at:

- Latitude: −23.0229° (23°01′22.8″ S)
- Longitude: −67.7552° (67°45′18.7″ W)
- Altitude: 5058 m

Units in `alma_positions.py` are **metres**. The Three.js scene applies a uniform scale factor to convert to scene units:

```js
// Scene.jsx (approximate — verify against source)
const SCALE = 1 / 30   // 1 scene unit ≈ 30 m
```

ALMA Y-array arms extend roughly ±600 m (DA pads) with a compact DV core within ±60 m. EHT nodes (α, β) are placed at arbitrary scene positions and do not correspond to real VLBI station coordinates.

### Standalone Telescopes

| ID | Position in scene | Notes |
|----|-------------------|-------|
| `apex` | ~200 m NE of array centre | APEX is 115 m from ALMA AOS in reality |
| `iram` | Offset south | IRAM 30m is in Spain — placed symbolically |
| `aste` | Offset east | |
| `nanten2` | Offset west | |
| `eht_alpha` | Far north | Symbolic VLBI node |
| `eht_beta` | Far south | Symbolic VLBI node |

> Standalone telescope positions in the scene are illustrative, not geographically accurate relative to ALMA.

---

## Open-Meteo Integration & Fallback

```
weather_fetcher.py polls every 5 minutes
  │
  ├── Success → parse JSON → derive PWV + τ₂₂₅GHz → cache result
  │     PWV  = f(temp, humidity) via Clausius-Clapeyron
  │     τ₂₂₅ = f(PWV) via Pardo et al. (2001) ATM model coefficients
  │
  └── Failure (network error, rate limit, timeout)
        → log WARNING
        → atmosphere_sim.py takes over for next tick(s)
        → retry resumes on next 5-minute poll interval (no backoff)

⚠ No explicit rate-limit handling — Open-Meteo free tier allows ~10,000
  calls/day (~1 call/8 s). At 1 call/5 min the quota is safe, but if the
  polling interval is reduced the caller should add a 429 backoff.
```