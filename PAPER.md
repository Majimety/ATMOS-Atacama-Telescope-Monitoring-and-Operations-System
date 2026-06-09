---
title: 'ATMOS: A High-Fidelity SCADA Simulation Platform for Radio Telescope Array Operations'
tags:
  - Python
  - JavaScript
  - radio astronomy
  - ALMA
  - telescope simulation
  - SCADA
  - education
  - interferometry
authors:
  - name: Jirayus Thongyos
    orcid: 0009-0008-6507-3522
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: 10 June 2026
bibliography: paper.bib
---

# Summary

ATMOS (Atacama Telescope Monitoring and Operations System) is an open-source,
high-fidelity SCADA (Supervisory Control and Data Acquisition) simulation
platform for real-time monitoring and control of radio telescope arrays modelled
on the Atacama Large Millimeter/submillimeter Array (ALMA). The system replicates
the full operational pipeline of a production observatory — from antenna-level
sensor telemetry through physically accurate atmospheric modelling to
operator-facing dashboards — using the same physical equations employed by real
ALMA operations software.

ATMOS is designed for two complementary purposes: as a **research prototype** for
exploring observatory control system architectures, and as an **educational tool**
enabling students and researchers to interact with a realistic radio telescope
environment without requiring access to actual observatory infrastructure.

# Statement of Need

Training operators and engineers for radio telescope facilities such as ALMA
requires hands-on experience with SCADA systems, interferometric data products,
and atmospheric constraint evaluation. Access to real telescope time for training
purposes is, however, severely limited by scheduling pressure and operational cost.
Existing simulation tools for radio astronomy typically focus on visibility
simulation (e.g., CASA `simobserve`) or signal processing, and do not reproduce
the real-time monitoring and control environment that operators encounter.

ATMOS fills this gap by providing a complete, self-contained simulation of the
ALMA operations environment that runs on a standard laptop. It exposes the same
conceptual interfaces — a SCADA control panel, telemetry dashboards, alert engine,
observation scheduler, UV-coverage visualisation, and baseline correlator — that
real operators use, enabling realistic training scenarios without telescope access.
The physically accurate models also make ATMOS suitable as a teaching aid for
graduate courses in radio astronomy and instrumentation.

# Physical Models

## System Temperature

The system noise temperature $T_\mathrm{sys}$ for each antenna is computed from
the standard radiometric equation [@ALMATechHandbook2023, Eq. 9.8–9.11]:

$$T_\mathrm{sys} = T_\mathrm{rx} + \eta \, T_\mathrm{atm}
  \left(1 - e^{-\tau_\mathrm{band} X}\right)
  + T_\mathrm{CMB} \, e^{-\tau_\mathrm{band} X}$$

where $T_\mathrm{rx}$ is the band-dependent receiver noise temperature (26–230 K
across ALMA Bands 1–10), $\eta = 0.95$ is the forward efficiency, $T_\mathrm{atm}
= 270\,\mathrm{K}$ is the effective atmospheric temperature at Chajnantor,
$T_\mathrm{CMB} = 2.73\,\mathrm{K}$, $\tau_\mathrm{band}$ is the band opacity,
and $X$ is the airmass.

## Atmospheric Opacity and PWV

Atmospheric opacity at 225 GHz is derived from Precipitable Water Vapour (PWV)
using the empirical relation of @Otarola2010:

$$\tau_{225} = 0.030 + 0.058 \times \mathrm{PWV}$$

PWV itself is estimated from live meteorological data (temperature, relative
humidity, surface pressure) retrieved from the Open-Meteo API at the ALMA/
Chajnantor coordinates (lat $-23.019°$, lon $-67.753°$, alt 5058 m), using the
Clausius–Clapeyron relation and hydrostatic integration following @Pardo2001.

## Airmass

The Kasten–Young (1989) formula is used in preference to the simple secant
approximation, providing accuracy to $\pm 0.1\%$ down to $5°$ elevation
[@Kasten1989]:

$$X = \frac{1}{\sin(\mathrm{el}) + 0.50572\,(\mathrm{el} + 6.07995)^{-1.6364}}$$

## UV-Coverage

Baseline vectors in the UV-plane are computed from the standard ENU→UVW
coordinate transform for each antenna pair $(i, j)$ [@Thompson2017]:

$$u = \Delta E \cos H - \Delta N \sin H$$
$$v = \Delta E \sin\delta \sin H + \Delta N \sin\delta \cos H - \Delta U \cos\delta$$

where $H$ is the hour angle and $\delta$ is the source declination. Both
$(u, v)$ and conjugate $(-u, -v)$ baselines are plotted, reflecting the
Hermitian symmetry of the visibility function. Antenna positions are derived
from the public ALMA C43-5 configuration data (CASA/NRAO).

# System Architecture

ATMOS follows a client–server architecture. The Python/FastAPI backend runs the
simulation engine and exposes a WebSocket endpoint that broadcasts a complete
system snapshot at 1 Hz to all connected clients simultaneously via
`asyncio.gather`. Each frame (~8–15 KB JSON) carries 64 per-dish states,
atmospheric parameters, scheduler state, and system metadata.

The React frontend renders four primary views: an interactive Three.js 3D scene
in which dish models animate Az/El pointing in real time; a SCADA dashboard with
live sparkline telemetry; a UV-coverage plot with hour-angle sweep animation; and
a baseline correlator with MAD-based RFI flagging. State is managed with Zustand
stores and the WebSocket connection is handled by a resilient client with
exponential backoff (1 s–60 s) and an IndexedDB offline buffer.

Access control is enforced through JWT/RBAC with four roles (viewer, operator,
engineer, admin) on both REST and WebSocket endpoints. Optional InfluxDB
integration enables persistent time-series storage with pre-built Grafana
dashboard templates.

# Features

ATMOS implements the following capabilities relevant to observatory operations
training and research:

- **Physically accurate Tsys** per dish, updated every second from live weather
- **Live meteorology** from Open-Meteo API with 5-minute cache and simulation fallback
- **Realistic pointing simulation** at ALMA specification slew rates (3°/s azimuth, 1.5°/s elevation) with settling phase
- **Priority-based observation scheduler** with real-time constraint evaluation (elevation, PWV, wind)
- **Rule-based alert engine** for dish faults, Tsys exceedances, wind, and PWV thresholds matching ALMA operational limits
- **Interferometric visualisations**: UV-coverage plot and N×N baseline correlator
- **Full REST API** with OpenAPI 3.1 documentation (Swagger UI)
- **Docker Compose** production stack with Traefik TLS, InfluxDB 2.7, Grafana 11, and Redis
- **pytest suite** with 43 test cases covering physics models, authentication, scheduler, WebSocket, and API layers

# Acknowledgements

The author thanks the ALMA Partnership (ESO/NAOJ/NRAO) for making antenna
configuration data, receiver specifications, and the ALMA Technical Handbook
publicly available. Aerial imagery of the ALMA array used in documentation is
credited to Juan Carlos Rojas (ALMA/ESO/NAOJ/NRAO). Live meteorological data
is provided by Open-Meteo (open-meteo.com) under an open-data license.

# References