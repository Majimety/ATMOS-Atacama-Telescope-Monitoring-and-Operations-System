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
on the Atacama Large Millimeter/submillimeter Array (ALMA). In plain terms,
ATMOS is an interactive dashboard that behaves like the control room software
used by professional radio observatory operators — but runs entirely on a
standard laptop without requiring access to real telescope hardware.

The system replicates the full operational pipeline of a production observatory:
antenna-level sensor telemetry, physically accurate atmospheric modelling,
interferometric science visualisations, and a priority-based observation
scheduler — all driven by the same physical equations used in real ALMA
operations software. A live Three.js 3D scene animates the dish array in real
time, while sparkline graphs, alert feeds, and a UV-coverage plot give users an
authentic observatory monitoring experience.

ATMOS is designed for two complementary purposes: as a **research prototype**
for exploring observatory control system architectures, and as an **educational
tool** enabling students and researchers to interact with a realistic radio
telescope environment without requiring access to actual observatory
infrastructure.

# Statement of Need

Training operators and engineers for radio telescope facilities such as ALMA
requires hands-on experience with SCADA systems, interferometric data products,
and atmospheric constraint evaluation. Access to real telescope time for
training purposes is, however, severely limited by scheduling pressure and
operational cost. A single hour of ALMA observing time represents a significant
fraction of a competitive proposal allocation; it cannot realistically be
dedicated to operator familiarisation.

Existing simulation tools for radio astronomy typically address a different
part of the pipeline. CASA `simobserve` [@CASA2022] generates synthetic
visibility data for imaging experiments but does not reproduce the real-time
monitoring and control environment that operators encounter. Similarly,
tools such as VLBI2010 simulators or beam-pattern calculators address specific
technical subsystems rather than the integrated SCADA experience.

ATMOS fills this gap by providing a complete, self-contained simulation of the
ALMA operations environment. It exposes the same conceptual interfaces — a
SCADA control panel, telemetry dashboards, alert engine, observation scheduler,
UV-coverage visualisation, and baseline correlator — that real operators use,
enabling realistic training scenarios without telescope access. The physically
accurate models also make ATMOS suitable as a teaching aid for graduate courses
in radio astronomy and instrumentation, where students can observe the effect of
changing receiver band, atmospheric PWV, or source elevation on system
sensitivity in real time.

The target audience includes observatory operations trainers, graduate students
in radio astronomy and instrumentation courses, and software engineers
developing observatory control systems who need a reference implementation of
the SCADA–telemetry–WebSocket pipeline.

# State of the Field

Several tools exist for radio astronomy simulation, but none address the
operational SCADA layer that ATMOS targets.

**CASA** [@CASA2022] is the standard package for ALMA and VLA data reduction.
Its `simobserve` task generates synthetic interferometric data from a sky model,
making it indispensable for proposal preparation and imaging algorithm
development. However, CASA operates offline on pre-defined observation
parameters and provides no real-time monitoring, telemetry streaming, or
operator control interface.

**ALMA Common Software (ACS)** is the actual control middleware used at the
observatory [@ACS2004]. It is a mature, production-grade distributed system but
requires the full ALMA computing infrastructure to operate and is not publicly
deployable for educational use.

**MeerKAT / MeerCRAB simulators** and similar facility-specific tools exist for
individual observatories but are tightly coupled to proprietary hardware
interfaces and are not designed for educational deployment.

ATMOS is distinguished by three characteristics that existing tools do not
combine: (1) it runs on a single laptop with no proprietary dependencies;
(2) it implements a complete, authenticated SCADA pipeline from WebSocket
telemetry through operator control to InfluxDB persistence; and (3) its physics
engine uses the same equations as production ALMA software, providing
scientifically meaningful outputs rather than placeholder data. Rather than
contributing to or replacing any existing tool, ATMOS occupies a distinct niche
as a self-contained educational and prototyping environment for the observatory
operations layer.

# Software Design

## Architecture Overview

ATMOS follows a client–server architecture motivated by the same separation of
concerns found in production observatory software. The Python/FastAPI backend
runs the simulation engine and exposes a WebSocket endpoint that broadcasts a
complete system snapshot at 1 Hz to all connected clients simultaneously via
`asyncio.gather`. Each JSON frame (~8–15 KB) carries 64 per-dish states,
atmospheric parameters, scheduler state, and system metadata.

The React frontend renders four primary views: an interactive Three.js 3D scene
in which dish models animate Az/El pointing in real time; a SCADA dashboard
with live sparkline telemetry; a UV-coverage plot with hour-angle sweep
animation; and a baseline correlator with MAD-based RFI flagging. State is
managed with Zustand stores and the WebSocket connection is handled by a
resilient client with exponential backoff (1 s–60 s) and an IndexedDB offline
buffer.

## Key Design Trade-offs

**WebSocket over REST polling.** A 1 Hz WebSocket broadcast was chosen over
REST polling because it eliminates the per-request HTTP overhead that would
otherwise dominate at high client counts, and because it matches the
push-based telemetry model used by real observatory SCADA systems. The
trade-off is that WebSocket connection management requires explicit dead-client
pruning, which is implemented in `ConnectionPool`.

**Per-dish physics vs. array-level approximation.** Each of the 64 antennas
has an independent `DishPointing` state machine and a separately computed Tsys
value. This per-dish model is more computationally expensive than an
array-average approximation but is necessary to faithfully reproduce fault
injection, elevation-dependent sensitivity variation, and the N×N baseline
correlator display.

**Live weather vs. pre-recorded climatology.** The system fetches real
meteorological data from the Open-Meteo API at the ALMA/Chajnantor coordinates
every five minutes, with a physics-based simulation fallback. This design
decision makes the atmospheric parameters genuinely time-varying and site-
realistic, at the cost of an external network dependency. The fallback ensures
that the system remains fully functional in offline or air-gapped environments.

**JWT/RBAC authentication.** A four-role access control model (viewer,
operator, engineer, admin) is enforced on both REST and WebSocket endpoints.
This design reflects the real ALMA role hierarchy and makes ATMOS suitable for
multi-user training scenarios where trainees should not have access to fault
injection or system shutdown commands.

## Physical Models

The system noise temperature $T_\mathrm{sys}$ for each antenna is computed from
the standard radiometric equation [@ALMATechHandbook2023, Eq. 9.8–9.11]:

$$T_\mathrm{sys} = T_\mathrm{rx} + \eta \, T_\mathrm{atm}
  \left(1 - e^{-\tau_\mathrm{band} X}\right)
  + T_\mathrm{CMB} \, e^{-\tau_\mathrm{band} X}$$

where $T_\mathrm{rx}$ is the band-dependent receiver noise temperature (26–230 K
across ALMA Bands 1–10), $\eta = 0.95$ is the forward efficiency, $T_\mathrm{atm}
= 270\,\mathrm{K}$ is the effective atmospheric temperature at Chajnantor,
$T_\mathrm{CMB} = 2.73\,\mathrm{K}$, $\tau_\mathrm{band}$ is the band opacity,
and $X$ is the airmass computed via the Kasten–Young (1989) formula
[@Kasten1989]:

$$X = \frac{1}{\sin(\mathrm{el}) + 0.50572\,(\mathrm{el} + 6.07995)^{-1.6364}}$$

Atmospheric opacity at 225 GHz is derived from Precipitable Water Vapour (PWV)
using the empirical relation of @Otarola2010:

$$\tau_{225} = 0.030 + 0.058 \times \mathrm{PWV}$$

PWV is estimated from live meteorological data via the Clausius–Clapeyron
relation and hydrostatic integration following @Pardo2001. Baseline vectors
in the UV-plane are computed from the standard ENU→UVW coordinate transform
[@Thompson2017]:

$$u = \Delta E \cos H - \Delta N \sin H$$
$$v = \Delta E \sin\delta \sin H + \Delta N \sin\delta \cos H - \Delta U \cos\delta$$

where $H$ is the hour angle and $\delta$ is the source declination. Antenna
positions are derived from the public ALMA C43-5 configuration data (CASA/NRAO).

# Research Impact Statement

ATMOS was developed as an independent open-source project and released publicly
on GitHub in 2025. As of the submission date the repository has attracted
community attention through its stars and has been linked from radio astronomy
education discussions online.

The software addresses a practical need that has been independently identified
by observatory trainers: the absence of a freely deployable, physics-accurate
SCADA simulator for the millimetre/submillimetre wavelength regime. ATMOS is
structured to support reproducible educational scenarios — the Docker Compose
stack allows a complete observatory environment (API, InfluxDB, Grafana,
Redis, Traefik) to be deployed with a single command, enabling instructors to
provide students with a consistent, isolated environment.

The pytest suite covers 43 test cases across the physics engine, authentication
system, scheduler, WebSocket layer, and REST API, providing a foundation for
reproducible verification of the physical models. The Grafana dashboard
templates bundled with the repository allow time-series results from simulation
sessions to be archived and compared across student cohorts.

Near-term impact pathways include adoption as a teaching tool in graduate
instrumentation courses at universities with radio astronomy programmes, and
as a reference implementation for researchers prototyping new observatory
scheduling or alert algorithms without requiring access to telescope time.

# AI Usage Disclosure

Generative AI tools (specifically Claude, by Anthropic) were used during the
development of ATMOS in the following capacities: drafting and refining inline
code comments and docstrings; reviewing code for logical errors and
inconsistencies; and assisting in the drafting and editing of this paper.

All AI-generated content was reviewed, verified, and where necessary corrected
by the author. Physical model equations were independently verified against the
cited reference documents (ALMA Technical Handbook Cycle 10, Kasten & Young
1989, Otarola et al. 2010, Pardo et al. 2001). Software logic was validated
against the 43-case pytest suite and manual end-to-end testing of the running
system.

# Acknowledgements

The author thanks the ALMA Partnership (ESO/NAOJ/NRAO) for making antenna
configuration data, receiver specifications, and the ALMA Technical Handbook
publicly available. Aerial imagery of the ALMA array used in documentation is
credited to Juan Carlos Rojas (ALMA/ESO/NAOJ/NRAO). Live meteorological data
is provided by Open-Meteo (open-meteo.com) under an open-data license. No
financial support was received for this work.

# References
