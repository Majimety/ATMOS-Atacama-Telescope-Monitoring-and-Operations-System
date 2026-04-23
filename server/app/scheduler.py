"""
scheduler.py — ATMOS Observation Scheduling Queue
==================================================

Manages a priority queue of observation jobs. Each job specifies a target,
required band, minimum elevation, maximum PWV, and estimated duration.

The scheduler runs as a background asyncio task, evaluating whether the
current atmospheric conditions and pointing constraints allow the next
job to execute. On each tick it:
  1. Checks if a job is actively running (and if it has completed)
  2. Evaluates the top-of-queue job against live constraints
  3. Emits status updates consumed by the WebSocket broadcast loop

Integration:
  - `get_queue_state()` → called by alma_sim.get_system_snapshot()
  - `add_job()` / `remove_job()` / `move_job()` → called by REST API
  - `_scheduler_tick()` → background asyncio task started in main.py
"""

import asyncio
import time
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class JobPriority(int, Enum):
    LOW    = 3
    NORMAL = 2
    HIGH   = 1      # lower number = higher priority in sort
    URGENT = 0


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ObservationJob:
    target_name: str
    ra: str
    dec: str
    az: float
    el: float
    band: int
    duration_s: int            # requested integration time in seconds
    min_el_deg: float = 15.0   # refuse if below this elevation
    max_pwv_mm: float = 3.0    # refuse if PWV exceeds this
    priority: JobPriority = JobPriority.NORMAL
    notes: str = ""

    # System-managed fields
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    elapsed_s: float = 0.0
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "job_id":        self.job_id,
            "target_name":   self.target_name,
            "ra":            self.ra,
            "dec":           self.dec,
            "az":            self.az,
            "el":            self.el,
            "band":          self.band,
            "duration_s":    self.duration_s,
            "min_el_deg":    self.min_el_deg,
            "max_pwv_mm":    self.max_pwv_mm,
            "priority":      self.priority.value,
            "priority_label": self.priority.name,
            "notes":         self.notes,
            "status":        self.status.value,
            "created_at":    self.created_at,
            "started_at":    self.started_at,
            "completed_at":  self.completed_at,
            "elapsed_s":     round(self.elapsed_s, 1),
            "progress_pct":  round(min(100, self.elapsed_s / max(1, self.duration_s) * 100), 1),
            "skip_reason":   self.skip_reason,
        }


# ── Scheduler state ───────────────────────────────────────────────────────────

class ObservationScheduler:
    def __init__(self):
        self._queue: list[ObservationJob] = []
        self._history: list[ObservationJob] = []
        self._active: Optional[ObservationJob] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._last_pwv: float = 0.5
        self._last_wind: float = 8.0

        # Pre-populate with demo jobs
        self._seed_demo_queue()

    def _seed_demo_queue(self):
        demo = [
            ObservationJob("Sgr A*",    "17h45m40s", "-29°00'28\"", 183.7, 52.4, 6,  3600, priority=JobPriority.HIGH,   notes="Galactic centre monitoring"),
            ObservationJob("M87",       "12h30m49s", "+12°23'28\"", 282.5, 28.1, 3,  7200, priority=JobPriority.NORMAL, notes="EHT follow-up, B3 continuum"),
            ObservationJob("Orion KL",  "05h35m14s", "-05°22'30\"",  93.2, 44.7, 6,  1800, priority=JobPriority.NORMAL, notes="Hot core chemistry survey"),
            ObservationJob("3C 273",    "12h29m06s", "+02°03'08\"", 187.3, 61.2, 7,  2700, priority=JobPriority.LOW,    notes="Quasar calibrator"),
            ObservationJob("Crab Nebula","05h34m31s", "+22°00'52\"",  84.1, 63.3, 3,  5400, min_el_deg=20.0, max_pwv_mm=2.0, priority=JobPriority.URGENT, notes="Pulsar timing — needs low PWV"),
        ]
        self._queue = demo

    # ── Queue operations ──────────────────────────────────────────────────────

    async def add_job(self, job: ObservationJob):
        async with self._lock:
            self._queue.append(job)
            self._sort_queue()
        logger.info(f"Scheduler: job added — {job.target_name} [{job.job_id}]")

    async def remove_job(self, job_id: str) -> bool:
        async with self._lock:
            before = len(self._queue)
            self._queue = [j for j in self._queue if j.job_id != job_id]
            return len(self._queue) < before

    async def move_job(self, job_id: str, direction: int):
        """Move job up (-1) or down (+1) in queue."""
        async with self._lock:
            idx = next((i for i, j in enumerate(self._queue) if j.job_id == job_id), None)
            if idx is None:
                return
            new_idx = max(0, min(len(self._queue) - 1, idx + direction))
            self._queue.insert(new_idx, self._queue.pop(idx))

    async def skip_active(self):
        """Abort the currently running job."""
        async with self._lock:
            if self._active:
                self._active.status = JobStatus.SKIPPED
                self._active.skip_reason = "Manually skipped by operator"
                self._history.append(self._active)
                self._active = None
        logger.warning("Scheduler: active job skipped by operator")

    def _sort_queue(self):
        """Sort by priority then creation time."""
        self._queue.sort(key=lambda j: (j.priority.value, j.created_at))

    # ── Constraint evaluation ─────────────────────────────────────────────────

    def _can_observe(self, job: ObservationJob) -> tuple[bool, Optional[str]]:
        """Return (ok, reason_if_not_ok)."""
        if job.el < job.min_el_deg:
            return False, f"Target elevation {job.el:.1f}° < minimum {job.min_el_deg:.1f}°"
        if self._last_pwv > job.max_pwv_mm:
            return False, f"PWV {self._last_pwv:.2f} mm > maximum {job.max_pwv_mm:.2f} mm"
        if self._last_wind > 25.0:
            return False, f"Wind {self._last_wind:.1f} m/s exceeds safe limit 25 m/s"
        return True, None

    # ── Tick (called every second by background task) ─────────────────────────

    async def tick(self, snapshot: dict):
        """Advance scheduler state by one telemetry tick."""
        atm = snapshot.get("atmosphere", {})
        self._last_pwv  = atm.get("pwv_mm",  self._last_pwv)
        self._last_wind = atm.get("wind_ms", self._last_wind)

        async with self._lock:
            # Advance active job
            if self._active:
                self._active.elapsed_s = time.time() - (self._active.started_at or time.time())
                if self._active.elapsed_s >= self._active.duration_s:
                    self._active.status = JobStatus.COMPLETED
                    self._active.completed_at = time.time()
                    logger.info(f"Scheduler: completed — {self._active.target_name}")
                    self._history.append(self._active)
                    self._active = None

            # Try to start next queued job
            if not self._active and self._queue:
                candidate = self._queue[0]
                ok, reason = self._can_observe(candidate)
                if ok:
                    candidate.status   = JobStatus.RUNNING
                    candidate.started_at = time.time()
                    self._active = self._queue.pop(0)
                    logger.info(f"Scheduler: started — {self._active.target_name} (band B{self._active.band})")
                else:
                    # Don't block forever — check periodically
                    candidate.skip_reason = reason

    # ── State export ──────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "active":  self._active.to_dict() if self._active else None,
            "queue":   [j.to_dict() for j in self._queue],
            "history": [j.to_dict() for j in self._history[-20:]],  # last 20
            "stats": {
                "queued":    len(self._queue),
                "completed": sum(1 for j in self._history if j.status == JobStatus.COMPLETED),
                "skipped":   sum(1 for j in self._history if j.status == JobStatus.SKIPPED),
            },
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
scheduler = ObservationScheduler()
