# ATMOS — Atacama Telescope Monitoring and Operations System

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](https://react.dev)
[![Three.js](https://img.shields.io/badge/Three.js-r184-black?logo=three.js)](https://threejs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

A high-fidelity **SCADA (Supervisory Control and Data Acquisition)** simulation platform for real-time monitoring and control of radio telescope arrays at the Atacama Desert Observatory. ATMOS replicates the operational environment of ALMA (Atacama Large Millimeter/submillimeter Array) and associated facilities, incorporating physically accurate atmospheric models, interferometric science visualizations, and a production-grade WebSocket telemetry pipeline.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Physical Models](#physical-models)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Simulated Facilities](#simulated-facilities)
- [Roadmap](#roadmap)
- [References](#references)

---

## Overview

ATMOS is designed as both a **research prototype** and an **educational tool** for radio observatory operations. The system simulates the complete telemetry pipeline from antenna-level sensor data through atmospheric modelling to operator-facing dashboards — using the same physical equations employed by real ALMA operations software.

Key distinguishing characteristics:

- **Physically accurate Tsys model** — implements the full radiometric equation from the ALMA Technical Handbook (Cycle 10), including band-dependent receiver temperatures, atmospheric opacity scaling, and Kasten-Young airmass correction
- **Real site meteorology** — integrates live weather data from Open-Meteo API at ALMA/Chajnantor coordinates (lat −23.019°, lon −67.753°, alt 5058 m), with PWV derived via the Clausius-Clapeyron relation
- **Interferometric science displays** — UV-coverage plot with ENU→UVW transform and baseline correlation matrix with RFI detection, implementing standard interferometry mathematics
- **Production infrastructure** — JWT/RBAC authentication, resilient WebSocket with exponential backoff, InfluxDB time-series integration, and Docker Compose deployment stack

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         BROWSER                              │
│                                                              │
│  ┌────────────┐  ┌───────────┐  ┌──────────┐   ┌──────────┐  │
│  │ 3D Scene   │  │ Dashboard │  │ UV-Plot  │   │Correlator│  │
│  │ (Three.js) │  │ (Zustand) │  │(Science) │   │(Science) │  │
│  └─────┬──────┘  └─────┬─────┘  └────┬─────┘   └────┬─────┘  │
│        └───────────────┴─────────────┴──────────────┘        │
│                              │                               │
│              Zustand Stores (telemetry, alerts, selection)   │
│                              │                               │
│              resilientWS.js (reconnect + IndexedDB buffer)   │
└──────────────────────────────┼───────────────────────────────┘
                               │  WebSocket  ws://:8000/ws/telemetry
┌──────────────────────────────┼───────────────────────────────┐
│                         FASTAPI                              │
│                              │                               │
│              ConnectionPool → broadcast(N clients, 1 Hz)     │
│                              │                               │
│             ( alma_sim.get_system_snapshot() )               │
│              │               │              │                │
│        physics_models  pointing_sim    weather_fetcher       │
│        (Tsys, τ, X)   (slew/track)   (Open-Meteo API)        │
└──────────────────────────────────────────────────────────────┘
```

WebSocket frames are broadcast at **1 Hz** to all connected clients simultaneously via `asyncio.gather`. Each frame carries the complete system snapshot (~50 antenna states + atmosphere + system metadata) serialised as JSON, typically 8–15 KB per frame.

---

## Physical Models

### System Temperature

The system noise temperature for each antenna is computed from the standard radiometric equation (ALMA Technical Handbook, Cycle 10, Eq. 9.8–9.11):

```
Tsys = T_rx + η · T_atm · (1 − e^(−τ_band · X)) + T_CMB · e^(−τ_band · X)
```

| Symbol | Definition | Value |
|--------|-----------|-------|
| T_rx | Receiver noise temperature (band-dependent) | 26–230 K |
| η | Forward efficiency | 0.95 |
| T_atm | Effective atmospheric temperature at Chajnantor | 270 K |
| T_CMB | Cosmic Microwave Background | 2.73 K |
| τ_band | Band opacity = τ_scale[band] × τ₂₂₅GHz | — |
| X | Airmass (Kasten-Young 1989) | sec(z) corrected |

### Atmospheric Opacity

Opacity at 225 GHz is derived from Precipitable Water Vapour (PWV) using the Danese-Partridge approximation:

```
τ₂₂₅ ≈ 0.04 · PWV + 0.012
```

PWV is estimated from in-situ meteorological data via the Clausius-Clapeyron relation and hydrostatic integration (Pardo et al. 2001, ATM model).

### Airmass

The Kasten-Young (1989) formula is used in preference to the simple secant approximation, providing accuracy to ±0.1% down to 5° elevation:

```
X = 1 / [sin(el) + 0.50572 · (el + 6.07995)^(−1.6364)]
```

### UV-Coverage

Baseline vectors in the UV-plane are computed from the ENU→UVW coordinate transform for each antenna pair (i, j):

```
u = dE · cos(H) − dN · sin(H)
v = dE · sin(δ)sin(H) + dN · sin(δ)cos(H) − dU · cos(δ)
```

where H is the hour angle and δ is source declination. Both (u, v) and conjugate (−u, −v) are plotted, reflecting the Hermitian symmetry of the visibility function.

---

## Features

### Operational (Implemented)

| Feature | Description |
|---------|-------------|
| **WebSocket Telemetry** | 1 Hz broadcast to N simultaneous clients via `asyncio.gather` with dead-connection pruning |
| **3D Array Visualisation** | Interactive Three.js scene — dishes animate Az/El in real time, click to inspect individual antenna |
| **Physically Accurate Tsys** | Per-dish system temperature from ALMA Technical Handbook radiometric equation |
| **Live Atmosphere** | PWV, τ₂₂₅GHz, wind, temperature from Open-Meteo API (Chajnantor lat/lon), 5-minute cache with simulation fallback |
| **Alert Engine** | Rule-based detection: dish offline, Tsys > 100/130 K, wind > 20/25 m/s, PWV > 2 mm, low elevation |
| **SCADA Control Panel** | Slew to Az/El, stow all, band selection (B1–B10), obs mode, fault injection |
| **UV-Coverage Plot** | Real ENU→UVW transform, band-scaled wavelength, HA sweep animation, angular resolution readout |
| **Baseline Correlator** | N×N visibility matrix, amplitude/phase toggle, MAD-based RFI flagging, fault annotation |
| **Pointing Simulation** | Realistic slew rate (2°/s az, 1°/s el), smooth interpolation, stow position El 15° |
| **JWT + RBAC** | Four-tier access control: viewer → operator → engineer → admin |
| **Resilient WebSocket** | Exponential backoff (1s–60s), IndexedDB offline buffer, data-gap detection, RTT display |
| **InfluxDB Integration** | `influx_writer.py` time-series writer + Flux schema + 24 h seed script |
| **Docker Compose** | Traefik + TLS, InfluxDB 2.7, Grafana 11, Redis, multi-stage Dockerfiles |
| **REST API** | Swagger UI at `/docs`, full OpenAPI 3.1 schema |
| **Sparkline Graphs** | Live Tsys, PWV, wind, τ history with configurable thresholds |
| **Dish Panel** | Scrollable antenna list with online/offline filter, sort by ID / Tsys / status |

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | React | 19.x |
| Build tool | Vite | 8.x |
| 3D rendering | Three.js + @react-three/fiber + drei | r184 / 9.x |
| State management | Zustand | 5.x |
| Charting | Recharts | 3.x |
| Backend framework | FastAPI + Uvicorn | 0.136 / 0.44 |
| Language | Python | 3.13 |
| Data validation | Pydantic | 2.x |
| Authentication | python-jose (JWT) + passlib (bcrypt) | — |
| Time-series DB | InfluxDB | 2.7 |
| Monitoring | Grafana | 11 |
| Cache / queue | Redis | 7 |
| Reverse proxy | Traefik | 3.1 |
| Containerisation | Docker + Compose | — |
| Weather API | Open-Meteo | — |

---

## Getting Started

### Prerequisites

- Python 3.11+ (tested on 3.13)
- Node.js 18+ and npm
- Git

### Development (local)

**1. Clone**
```bash
git clone https://github.com/Majimety/ATMOS-Atacama-Telescope-Monitoring-and-Operations-System.git
cd ATMOS-Atacama-Telescope-Monitoring-and-Operations-System
```

**2. Backend**
```bash
cd server
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`
Interactive API docs: `http://localhost:8000/docs`

**3. Frontend** (new terminal)
```bash
cd client
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`

### Production (Docker)

```bash
cp .env.example .env          # configure secrets and domain
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up -d
```

Services: ATMOS API, Nginx frontend, InfluxDB, Grafana, Redis, Traefik (TLS auto-provisioned via Let's Encrypt).

---

## API Reference

Full interactive documentation is available at `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc).

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | System status and version |
| `GET` | `/health` | Health check with current pointing state |
| `POST` | `/api/slew` | Command array to Az/El (body: `{az, el}`) |
| `POST` | `/api/stow` | Stow all antennas to El 15° |
| `POST` | `/api/band/{band}` | Set receiver band (1–10) |
| `POST` | `/api/mode/{mode}` | Set observation mode |
| `POST` | `/api/fault` | Inject or clear antenna fault |

### WebSocket

**Endpoint:** `ws://localhost:8000/ws/telemetry`

**Server → Client** (1 Hz, JSON):
```json
{
  "timestamp": "2025-04-23T07:15:00.000Z",
  "system":    { "band": 6, "freq_ghz": 230, "obs_mode": "interferometry", "target_name": "Sgr A*", ... },
  "atmosphere":{ "pwv_mm": 0.52, "tau_225ghz": 0.033, "wind_ms": 8.4, "temp_c": -6.2, "source": "live" },
  "alma":      { "dishes": [...], "online_count": 63, "total_count": 64, "avg_tsys_k": 80.5 },
  "pointing_mode": "tracking"
}
```

**Client → Server** (commands):
```json
{ "type": "slew",         "az": 183.7, "el": 52.4, "target_name": "Sgr A*" }
{ "type": "stow" }
{ "type": "set_band",     "band": 7 }
{ "type": "set_mode",     "mode": "vlbi" }
{ "type": "inject_fault", "dish_id": "B005", "offline": true }
```

---

## Simulated Facilities

### ALMA Array (primary)

| Pad series | Arm | Max baseline | Antenna type |
|-----------|-----|-------------|-------------|
| A001–A006 | Central core | ~40 m | DA / DV |
| B001–B014 | Northeast (~60°) | ~900 m | DA / DV |
| C001–C014 | Northwest (~300°) | ~1050 m | DA / DV |
| D001–D014 | South (~180°) | ~1300 m | DA / DV |
| ACA01–ACA12 | Compact (Morita) | ~50 m | CM (7 m) |

Positions derived from ALMA C43-5 configuration (CASA/NRAO public data). Angular resolution at Band 6 (230 GHz) with 1.3 km baseline: **θ ≈ λ/B_max ≈ 0.23 arcsec**.

### ALMA Receiver Bands Simulated

| Band | Frequency | Typical Tsys | Primary science use |
|------|-----------|-------------|-------------------|
| B3 | 84–116 GHz | 45 K | CO(1-0), HCN, dense gas tracers |
| B6 | 211–275 GHz | 55 K | CO(2-1), dust continuum *(most used)* |
| B7 | 275–370 GHz | 75 K | HCO⁺, submillimetre continuum |
| B9 | 602–720 GHz | 175 K | Near 620 GHz H₂O line |

All 10 ALMA bands (B1–B10) are selectable in the control panel.

---

## Roadmap

### Near-term

- [ ] **Observation scheduling queue** — queue-based target sequencing with elevation constraints and time estimates
- [ ] **InfluxDB live writer activation** — connect `influx_writer.py` to the WebSocket broadcast loop for persistent telemetry history
- [ ] **Grafana dashboard templates** — pre-built panels for Tsys trends, PWV history, and array health over time
- [ ] **Auth UI** — login modal and role indicator in the dashboard header

### Medium-term

- [ ] **Source catalogue integration** — searchable catalogue (Simbad/NED API) for target selection by name
- [ ] **Observation sensitivity calculator** — estimate RMS noise as a function of bandwidth, integration time, Tsys, and number of antennas
- [ ] **WebSocket auth** — extend JWT validation to the `/ws/telemetry` endpoint (currently open)
- [ ] **Multi-array mode** — toggle between ALMA, APEX, and EHT node displays

### Long-term

- [ ] **Real correlator interface** — replace `simulateVisibilities()` in `BaselineCorrelator.jsx` with a live data feed
- [ ] **VLBI fringe detection** — simulate fringe rate and delay search for EHT-style VLBI baselines
- [ ] **Commissioning mode** — holography, pointing model fitting, and receiver tuning workflows

---

## Project Structure

```
ATMOS/
├── server/
│   ├── main.py                   FastAPI application + REST routes
│   ├── auth.py                   JWT authentication + RBAC (4 roles)
│   ├── influx_writer.py          InfluxDB time-series writer
│   ├── requirements.txt
│   └── app/
│       ├── models/
│       │   ├── telescope.py      Pydantic data models
│       │   └── telemetry.py      ConnectionPool (WebSocket manager)
│       ├── simulation/
│       │   ├── alma_sim.py       Simulation engine + snapshot builder
│       │   ├── alma_positions.py Real ALMA C43-5 pad coordinates (ENU)
│       │   ├── physics_models.py Tsys, airmass, signal computations
│       │   ├── pointing_sim.py   Slew/track motion controller
│       │   ├── atmosphere_sim.py Fallback atmospheric simulation
│       │   └── weather_fetcher.py Open-Meteo API client + PWV derivation
│       ├── ws/
│       │   ├── telemetry.py      WebSocket endpoint + command dispatch
│       │   └── events.py         Event type constants
│       └── api/
│           ├── telescopes.py     REST: antenna listing
│           ├── atmosphere.py     REST: meteorological data
│           └── control.py        REST: slew / stow / band / fault
├── client/src/
│   ├── App.jsx                   Root layout + tab navigation
│   ├── hooks/
│   │   ├── useWebSocket.js       WebSocket connection hook
│   │   └── useTelemetry.js       Snapshot → store → alert pipeline
│   ├── store/
│   │   ├── telemetryStore.js     Zustand: live snapshot + 2-min history
│   │   ├── alertStore.js         Zustand: alert queue (max 300 events)
│   │   ├── alertEngine.js        Rule-based alert detection
│   │   ├── telescopeStore.js     Zustand: dish selection + filter state
│   │   └── auth.js               Authentication state
│   ├── components/
│   │   ├── Dashboard.jsx         System status overview panel
│   │   ├── TelescopePanel.jsx    Scrollable antenna list
│   │   ├── ControlPanel.jsx      SCADA control interface
│   │   ├── TelemetryGraphs.jsx   Live sparkline graphs
│   │   ├── AlertFeed.jsx         Event log with severity triage
│   │   ├── UVCoveragePlot.jsx    UV-plane visualisation (interferometry)
│   │   └── BaselineCorrelator.jsx Visibility matrix + RFI flagging
│   ├── three/
│   │   ├── Scene.jsx             Three.js canvas
│   │   ├── DishMesh.jsx          Antenna 3D model (Az/El animation)
│   │   ├── SkyDome.jsx           Night sky + sidereal star rotation
│   │   └── TerrainMesh.jsx       Atacama plateau terrain
│   └── libs/
│       └── resilientWS.js        WebSocket: backoff, buffer, gap detect
├── docker/
│   ├── docker-compose.yml        Full production stack
│   ├── Dockerfile.server         FastAPI container (multi-stage)
│   └── Dockerfile.client         Nginx + Vite build container
├── influx/
│   ├── schema.flux               Flux query examples for InfluxDB
│   └── seed.py                   Seed 24 h of historical telemetry
├── ARCHITECTURE.md               Detailed system architecture
├── TELESCOPE_DATA.md             Physical parameters and reference data
└── .env.example                  Environment variable template
```

---

## References

1. ALMA Partnership. *ALMA Technical Handbook, Cycle 10*. ALMA Observatory, 2023. [alma-telescope.org](https://almascience.nrao.edu/documents-and-tools)
2. Kasten, F. and Young, A. T. (1989). "Revised optical air mass tables and approximation formula." *Applied Optics*, 28(22), 4735–4738. [doi:10.1364/AO.28.004735](https://doi.org/10.1364/AO.28.004735)
3. Pardo, J. R., Cernicharo, J. and Serabyn, E. (2001). "Atmospheric transmission at microwaves (ATM): an improved model for millimeter/submillimeter applications." *IEEE Transactions on Antennas and Propagation*, 49(12), 1683–1694.
4. Otarola, A. et al. (2010). "Precipitable Water Vapor, Temperature, and Wind Statistics At Sites Suitable for mm and Submm Wavelength Astronomy in Northern Chile." *PASP*, 122(897), 1333. [doi:10.1086/657267](https://doi.org/10.1086/657267)
5. Thompson, A. R., Moran, J. M. and Swenson, G. W. (2017). *Interferometry and Synthesis in Radio Astronomy*, 3rd ed. Springer. ISBN 978-3-319-44431-4.

---

## License

MIT © 2025 — see [LICENSE](LICENSE) for details.