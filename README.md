# PlagioScale

PlagioScale is a cloud-native, microservices-based plagiarism detection platform that demonstrates a production-like architecture suitable for local development and testing.

Key ideas: lightweight API, Redis-backed queue, background workers, and a React + Vite frontend for submissions and teacher dashboards.

Live demo status: the repository includes Docker Compose orchestration that launches the full stack (Postgres, Redis, API, worker, frontend). The project has been verified end-to-end: create an assignment, upload ≥2 submissions, run similarity compute, and fetch the resulting matrix.

---

Table of Contents

- Overview
- Quick Start (Docker)
- Local Development (Python & Frontend)
- Architecture
- Configuration & Environment Variables
- Troubleshooting
- What's changed (recent fixes)
- Contributing
- License

---

## Overview

PlagioScale implements a k-shingle + cosine similarity pipeline to detect text overlap across student submissions. It is intentionally small and modular to let you iterate on algorithms, scale workers, or integrate monitoring and autoscaling.

## Quick Start (recommended — Docker)

Prerequisites:

- Docker Desktop

Start the full stack:

```bash
docker compose up -d --build
```

Services started by the compose file include:

- Redis (queue)
- Postgres (storage)
- API Service (FastAPI) on port 8000
- Worker Service (background jobs)
- Frontend (Vite/React) on port 5173 (dev) or served via Docker

Smoke-test flow (what to try first):

1. Create an assignment via the teacher portal.
2. Upload at least two submissions (student portal).
3. Click "Compute similarity" on the teacher dashboard.
4. Wait for worker completion and view the similarity matrix.

## Local Development (Python backend)

If you prefer running services locally without Docker, create a Python virtual environment and install consolidated dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirementsall.txt
```

Caveats:

- On Windows you may need Visual C++ Build Tools and, for some packages, Rust toolchain. To avoid native builds, match the Python version used by Docker (Python 3.11) or use the provided pinned `requirementsall.txt` which favors wheel-compatible versions.
- You must run Redis and Postgres locally and export correct env vars (see Configuration below).

## Frontend (React + Vite)

Development:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API base URL to be available via `VITE_API_BASE` (defaults to `http://localhost:8000`).

To build for production:

```bash
cd frontend
npm run build
```

## Architecture (high level)

User → API (FastAPI) → Redis Queue → Worker(s) → Postgres + results

-+- API: Receives submissions and management actions (create assignment, submit file, request compute).

- Queue: Redis list + job metadata for reliable handoff to workers.
- Workers: dequeue jobs, extract text, vectorize, compute pairwise similarity, store results.

## Configuration & Environment Variables

When running with Docker Compose, the compose file sets sensible defaults. For local runs you'll need to set:

- `DATABASE_URL` or `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `REDIS_HOST` (set to `localhost` for local Redis)
- `VITE_API_BASE` (frontend dev server)

## Troubleshooting

- If API or worker crashes with `ModuleNotFoundError: No module named 'psycopg'` — ensure service requirements use `psycopg[binary]` and rebuild images: `docker compose up -d --build api-service worker`.
- If dependency builds fail on Windows, match Docker's Python version (3.11) or install Visual C++ Build Tools and Rust to compile wheels.
- Frontend shows "Computing..." indefinitely if a compute request was issued with fewer than two submissions — the API now rejects such requests with a clear 400 error. Upload ≥2 submissions before computing.

## What's changed (recent fixes performed)

- Consolidated dependencies into `requirementsall.txt` to simplify venv installs.
- Added `scripts/setup_env.ps1` to automate local venv creation and installs.
- Replaced legacy DB driver with `psycopg[binary]` and aligned service `requirements.txt` files.
- Added server-side preflight validation for compute requests (rejects batches with <2 submissions).
- Surfaced backend errors to the teacher dashboard to avoid indefinite spinners.
- Rebuilt Docker images and verified end-to-end smoke test (assignment → upload 2 submissions → compute → matrix).

## Contributing

Contributions are welcome. Please open issues for bugs or feature requests and submit PRs for fixes. Keep changes small and focused — prefer adding tests for new behavior.

Suggested local dev flow:

1. Start Redis and Postgres locally or via Docker Compose.
2. Run API and worker in your IDE using the `.venv`.
3. Run frontend with `npm run dev` and set `VITE_API_BASE` to your API.

## License & Contact

This repository is provided as-is for educational and demonstration purposes. Include your preferred license here.

---

If you'd like, I can:

- open a PR with this updated README and the removal of `frontend/README.md`;
- add a short banner in the teacher dashboard reminding users to upload at least two submissions before computing.

---
