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

Radio telescope arrays like the Atacama Large Millimeter/submillimeter Array
(ALMA) in Chile are among the most complex scientific instruments ever built.
Operating them requires a continuous stream of data from dozens of antennas —
temperatures, wind speeds, atmospheric conditions, pointing positions — flowing
into a control room where operators monitor everything in real time. The
software that manages this is called a SCADA (Supervisory Control and Data
Acquisition) system.

ATMOS is an open-source simulation of that environment. It replicates the
experience of sitting at an ALMA control console: dishes animate in 3D as
they slew to new targets, atmospheric conditions update from real weather data
at the Chajnantor plateau, alerts fire when a dish goes offline, and an
observation scheduler queues up targets by priority. All of this runs on a
standard laptop, with no telescope access required.

The system uses the same physical equations found in real ALMA operations
software, making it useful not just as a demo but as a teaching tool for
graduate students in radio astronomy and as a prototyping environment for
engineers designing observatory control systems.

# Statement of Need

Training operators for facilities like ALMA is difficult. Real telescope time
is expensive and competitively allocated — it cannot realistically be set aside
for familiarisation exercises. Existing simulation tools for radio astronomy,
such as CASA `simobserve` [@CASA2022], focus on generating synthetic visibility
data for imaging experiments. They do not reproduce the real-time monitoring
and control experience that operators actually encounter.

ATMOS addresses this gap. It provides a complete, self-contained simulation of
the ALMA operations environment — a SCADA control panel, live telemetry
dashboards, an alert engine, an observation scheduler, a UV-coverage plot, and
a baseline correlator — that can be deployed with a single Docker command on
any laptop. Students can observe in real time how changing the receiver band,
the source elevation, or the atmospheric water vapour content affects system
sensitivity. Operators in training can practice fault injection and recovery
without touching real hardware.

The target users are graduate students in radio astronomy and instrumentation
courses, observatory operations trainers who need a deployable simulator, and
software engineers prototyping new SCADA or scheduling algorithms.

# State of the Field

Several tools exist for radio astronomy simulation, but none address the
operational SCADA layer that ATMOS targets.

CASA [@CASA2022] is the standard package for ALMA and VLA data reduction. Its
`simobserve` task is indispensable for proposal preparation and imaging
algorithm development, but it operates offline on pre-defined parameters and
provides no real-time control interface. ALMA Common Software (ACS)
[@ACS2004] is the actual middleware used at the observatory; it requires the
full ALMA computing infrastructure and is not publicly deployable for
educational use. Facility-specific simulators for other arrays (MeerKAT, VLA)
exist but are tightly coupled to proprietary hardware interfaces.

ATMOS is distinct in combining three things that no existing tool offers
together: it runs on a single laptop with no proprietary dependencies; it
implements a complete authenticated SCADA pipeline from WebSocket telemetry
through operator control to InfluxDB time-series persistence; and its physics
engine uses the same equations as production ALMA software, producing
scientifically meaningful outputs rather than placeholder values.

# Software Design

ATMOS follows a client–server architecture that mirrors the separation of
concerns found in production observatory software. The Python/FastAPI backend
runs the simulation engine and broadcasts a complete system snapshot at 1 Hz
to all connected clients via WebSocket. Each JSON frame (~8–15 KB) carries
per-dish states for all 64 antennas, atmospheric parameters, scheduler state,
and system metadata. The React frontend renders four primary views: an
interactive Three.js 3D scene with real-time Az/El animation; a SCADA
dashboard with sparkline telemetry; a UV-coverage plot with hour-angle sweep;
and a baseline correlator with MAD-based RFI flagging.

A WebSocket broadcast was chosen over REST polling because it eliminates
per-request HTTP overhead and matches the push-based telemetry model used by
real observatory SCADA systems. Each of the 64 antennas has an independent
pointing state machine and a separately computed system temperature, which is
necessary to faithfully reproduce fault injection, elevation-dependent
sensitivity variation, and the N×N baseline correlator display.

Live meteorological data is fetched from the Open-Meteo API at the ALMA/
Chajnantor coordinates (lat $-23.019°$, lon $-67.753°$, alt 5058 m) every
five minutes, with a physics-based diurnal simulation as fallback. This
makes the atmospheric parameters genuinely time-varying while keeping the
system fully functional offline.

## Physical Models

The system noise temperature $T_\mathrm{sys}$ for each antenna is computed
from the standard radiometric equation [@ALMATechHandbook2023, Eq. 9.8–9.11]:

$$T_\mathrm{sys} = T_\mathrm{rx} + \eta \, T_\mathrm{atm}
  \left(1 - e^{-\tau_\mathrm{band} X}\right)
  + T_\mathrm{CMB} \, e^{-\tau_\mathrm{band} X}$$

where $T_\mathrm{rx}$ is the band-dependent receiver noise temperature
(26–230 K across ALMA Bands 1–10), $\eta = 0.95$ is the forward efficiency,
$T_\mathrm{atm} = 270\,\mathrm{K}$ is the effective atmospheric temperature
at Chajnantor, and $T_\mathrm{CMB} = 2.73\,\mathrm{K}$. Airmass $X$ is
computed via the Kasten–Young formula [@Kasten1989]:

$$X = \frac{1}{\sin(\mathrm{el}) + 0.50572\,(\mathrm{el} + 6.07995)^{-1.6364}}$$

Atmospheric opacity at 225 GHz is derived from Precipitable Water Vapour
(PWV) using the empirical relation of @Otarola2010, with PWV estimated from
live meteorological data via the Clausius–Clapeyron relation and hydrostatic
integration following @Pardo2001. Baseline vectors in the UV-plane are
computed from the standard ENU→UVW coordinate transform [@Thompson2017],
using antenna positions from the public ALMA C43-5 configuration.

A four-role access control model (viewer, operator, engineer, admin) is
enforced on both REST and WebSocket endpoints, reflecting the real ALMA role
hierarchy and making ATMOS suitable for multi-user training scenarios.

# Research Impact Statement

ATMOS was released publicly on GitHub in 2025 as an independent open-source
project. The software fills a practical gap that has been independently
noted by observatory trainers: the absence of a freely deployable,
physics-accurate SCADA simulator for the millimetre/submillimetre wavelength
regime.

The Docker Compose stack deploys a complete observatory environment — API,
InfluxDB, Grafana, Redis, Traefik — with a single command, allowing
instructors to provide students with a consistent, isolated training
environment. Pre-built Grafana dashboard templates allow simulation session
results to be archived and compared across student cohorts, supporting
reproducible classroom experiments.

The pytest suite covers 43 test cases across the physics engine,
authentication system, scheduler, WebSocket layer, and REST API, providing
a verifiable foundation for the physical model implementations. Near-term
impact pathways include adoption in graduate instrumentation courses and
as a reference implementation for researchers prototyping observatory
scheduling or alerting algorithms.

# AI Usage Disclosure

Generative AI tools were used during the development of ATMOS, specifically
Claude and Claude Code (Anthropic). These tools assisted with drafting and
refining code comments and docstrings, and reviewing code for logical errors
and inconsistencies.

All AI-generated content was reviewed and verified by the author. Physical
model equations were independently checked against the cited reference
documents. Software logic was validated against the 43-case pytest suite and
manual end-to-end testing of the running system.

# Acknowledgements

The author thanks the ALMA Partnership (ESO/NAOJ/NRAO) for making antenna
configuration data, receiver specifications, and the ALMA Technical Handbook
publicly available. Aerial imagery of the ALMA array used in documentation
is credited to Juan Carlos Rojas (ALMA/ESO/NAOJ/NRAO). Live meteorological
data is provided by Open-Meteo (open-meteo.com) under an open-data license.
No financial support was received for this work.

# References