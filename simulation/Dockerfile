FROM python:3.12-slim

# WORKDIR is the *parent* of the simulation package (mirrors backend's own
# Dockerfile: WORKDIR /app, package at /app/app) — `import simulation.x`
# needs a directory literally named simulation on the path, not its
# contents flattened into the workdir.
WORKDIR /app

# Backend is a local editable dependency (Decision 1: single source of
# truth for domain services and shared dependency versions) — the build
# context is the repo root so this can see ../backend.
COPY backend /backend
COPY simulation/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e /backend

COPY simulation ./simulation

# Not a long-running server — a job container. `docker compose exec
# simulation python -m simulation.<entrypoint>` runs an actual generation.
CMD ["sleep", "infinity"]
