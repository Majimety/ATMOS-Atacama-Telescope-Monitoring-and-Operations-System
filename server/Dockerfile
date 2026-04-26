###############################################################################
# server/Dockerfile  —  ATMOS FastAPI backend
# Multi-stage: builder installs deps, final image is lean
###############################################################################
FROM python:3.13-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS final

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH"

COPY --from=builder /install /install
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" atmos
USER atmos

EXPOSE 8000

# Single worker is intentional.
#
# ATMOS uses in-process singletons for the observation scheduler
# (ObservationScheduler) and the InfluxDB writer (InfluxWriter).  Running
# multiple uvicorn workers via --workers N forks the process, giving each
# worker its own copy of these objects.  The scheduler state (active job,
# queue, history) and the InfluxDB write buffer would then diverge across
# workers, producing split-brain behaviour: one worker may believe a job is
# running while another starts the same job independently.
#
# To scale horizontally, migrate scheduler state and the write buffer to Redis
# (already provisioned in docker-compose.yml) and replace the singleton
# references accordingly, then re-enable --workers N.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--loop", "uvloop", "--log-level", "warning"]

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"