# PlagioScale — Full Setup & Demo Guide

> This guide covers everything needed to get **PlagioScale** running on a bare laptop for demonstration purposes. It is designed so that any AI agent can follow the steps and make informed decisions to adapt to the specific device.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Getting the Code](#2-getting-the-code)
3. [First-Time Build & Run](#3-first-time-build--run)
4. [Verifying Everything Is Up](#4-verifying-everything-is-up)
5. [Demo Walkthrough](#5-demo-walkthrough)
6. [Architecture Overview](#6-architecture-overview)
7. [Key Features to Show](#7-key-features-to-show)
8. [Troubleshooting](#8-troubleshooting)
9. [Appendix: Service Reference](#9-appendix-service-reference)

---

## 1. Prerequisites

### Required Software

| Software | Min Version | Notes |
|---|---|---|
| **Docker** | 24.x+ | Docker Desktop (Windows/Mac) or Docker CE (Linux) |
| **Docker Compose** | 2.20+ | Included with Docker Desktop; install separately on Linux |
| **Git** | 2.x+ | To clone the repository |
| **At least 6 GB free RAM** | — | Docker services: ~4 GB total. Worker peaks at ~2 GB during model loading |
| **At least 15 GB free disk** | — | Docker images (~5 GB), model cache (~3 GB), volumes |

### Optional but Recommended

| Tool | Purpose |
|---|---|
| Python 3.14+ | Running seed data / stress test scripts outside Docker |
| Node.js 24+ | Frontend development (not needed for demo — Nginx serves the build) |

### Ports to Keep Free

| Port | Service |
|---|---|
| 3050 | Frontend (Nginx) |
| 8000 | API service |
| 8002 | Autoscaler |
| 8090 | Monitoring dashboard |
| 3000 | Grafana |
| 9090 | Prometheus |
| 5432 | PostgreSQL |
| 6379 | Redis |

If a port is in use, edit `docker-compose.yml` to change the host-side mapping (e.g. `"3051:80"`).

---

## 2. Getting the Code

```bash
# Clone the repository (if not already present)
git clone <repo-url> PlagioScale
cd PlagioScale

# Checkout the stable demo-ready branch
git checkout main
```

**Important:** The `main` branch is the stable, demo-ready release. The `refactor` branch contains in-progress improvements. For presentations, always use `main`.

---

## 3. First-Time Build & Run

### 3.1 Environment Configuration

```bash
# Copy the example env file (defaults work out of the box)
cp .env.example .env
```

The default `.env` values are pre-configured for local Docker Compose usage. Key defaults:

| Variable | Default | Notes |
|---|---|---|
| `DB_PASSWORD` | `plagio_pass` | PostgreSQL |
| `REDIS_PASSWORD` | `plagio_redis_pass` | Redis |
| `JWT_SECRET` | `change-this-to-a-random-64-char-string` | Change for production |
| `VITE_API_BASE` | `http://localhost:8000` | Frontend-to-API URL |

### 3.2 Build and Start All Services

```bash
# Build and start everything
docker compose up -d --build

# Expected: 9 containers (10 with --build for worker build cache)
# - postgres, redis, api-service, worker, frontend,
#   autoscaler, monitoring-service, prometheus, alertmanager, grafana
```

**What happens during the build:**

| Service | Build Time | Disk | Notes |
|---|---|---|---|
| **worker** | 5–15 min | ~3.5 GB | Downloads PyTorch + HuggingFace models (SBERT, RoBERTa, DistilGPT2). First build is slowest. |
| **api-service** | 1–2 min | ~300 MB | Pure Python dependencies |
| **frontend** | 1–2 min | ~200 MB | NPM install + Vite build |
| Other services | <1 min each | ~50–150 MB each | |

### 3.3 Wait for Readiness

```bash
# Check all containers are running
docker compose ps

# Watch logs for initialization progress
docker compose logs -f api-service
docker compose logs -f worker
```

The worker container will show model loading progress:
```
worker  | [INFO] Warming up models...
worker  | [INFO] Loading DistilGPT2 for perplexity scoring...
worker  | [INFO] Loading SBERT model for semantic similarity...
```

**Allow 30–60 seconds** after the worker reports "warmup complete" for everything to stabilize.

### 3.4 Quick Smoke Test

```bash
# API health check
curl http://localhost:8000/health

# Frontend is serving
curl -s -o /dev/null -w "%{http_code}" http://localhost:3050
# Should return 200
```

---

## 4. Verifying Everything Is Up

Open these URLs in a browser:

| URL | What You See |
|---|---|
| http://localhost:3050 | **PlagioScale Home** — landing page |
| http://localhost:8000/health | **API health** — JSON with service status |
| http://localhost:8000/docs | **Swagger UI** — interactive API docs |
| http://localhost:8090 | **Monitoring Dashboard** — live metrics |
| http://localhost:3000 | **Grafana** — dashboards (login: `admin` / `admin`) |
| http://localhost:9090 | **Prometheus** — metrics explorer |

---

## 5. Demo Walkthrough

### 5.1 Create an Account

1. Go to http://localhost:3050
2. Click **Login / Sign up**
3. Click **Need an account?** to switch to signup mode
4. Enter: Email (e.g. `teacher@demo.com`), Name (e.g. `Professor Demo`), Password (min 6 chars)
5. Click **Create account**
6. You are automatically redirected to the Dashboard

### 5.2 Create an Assignment Batch

1. On the Dashboard, in the left panel, enter an **Assignment Name** (e.g. `Essay 1 - Literature Review`)
2. Set **Expected submissions** to e.g. `10`
3. Click **Create assignment**
4. A new batch is created — note the **Access Code** displayed in the detail panel on the right. This code will be shared with students.

### 5.3 Submit Sample Files (as Students)

You can submit files in two ways:

**Option A — Student Submit page (no login needed):**
1. Go to http://localhost:3050/student
2. Enter a **Roll Number** (e.g. `1001`)
3. Enter the **Access Code** from step 5.2
4. Upload a `.txt`, `.docx`, or `.pdf` file
5. Repeat with different roll numbers (e.g. `1002`, `1003`) using the same access code
6. Submit at least **2 files** so similarity computation runs

**Option B — Use seed data script:**
```bash
# Generate 2 batches with 5 students each
docker compose exec api-service python scripts/seed_test_data.py
```

### 5.4 Compute Similarity

1. Go back to http://localhost:3050/dashboard
2. Select the assignment from the left panel
3. Click **Compute similarity** (top-right of the detail panel)
4. A progress bar appears at the top: `Progress: X / Y submissions processed`
5. Wait for completion (2–60 seconds depending on file sizes and model loading)
6. The **Similarity Matrix** appears below the submissions table

### 5.5 Explore Results

**Similarity Matrix:**
- Each cell shows the similarity score (0.00 to 1.00) between two submissions
- Color scale: white (0) → red (1.00)
- Click any cell (except diagonal `—`) to open the **Matrix Viewer** modal
- The modal shows side-by-side text comparison

**AI Detection Badges:**
- Each row in the submissions table shows an AI score badge
- Green: <30% AI probability
- Yellow: 30–70%
- Red: >70%

**Collusion Graph:**
- Appears automatically when ≥3 submissions exist
- Nodes connected by edges for similarity ≥0.5
- Edge color intensity = similarity strength

**Blind Review Toggle:**
- Toggle in the header to anonymise student names (replaced with "Submission N")

**Cross-Batch Comparison:**
- Navigate to http://localhost:3050/cross-batch
- Select two different batches to compare submissions across them

**Student Comparison:**
- From the Student Dashboard, click "View" on any submission to see its pairwise scores

### 5.6 Admin Panel

1. First, promote your user to admin via the API:
```bash
# Get your user ID from the stats endpoint
curl http://localhost:8000/admin/stats -H "Authorization: Bearer $(docker compose exec api-service python -c "print('ask-admin-to-get-token')")"

# Alternative: use direct DB access
docker compose exec postgres psql -U plagio -d plagioscale -c "UPDATE users SET role='admin' WHERE email='teacher@demo.com'; UPDATE users SET token_version=token_version+1 WHERE email='teacher@demo.com';"
```
2. Log out and log back in (session invalidation on role change)
3. Go to http://localhost:3050/admin
4. Explore:
   - **Stats tab** — system-wide statistics
   - **Users tab** — search, paginate, change roles
   - **Notifications tab** — send pending email notifications
   - **Audit tab** — live SSE-streamed audit log

### 5.7 Export Results

- **CSV Export:** Click **Export CSV** button on the dashboard detail panel
- **PDF Report:** Open the Matrix Viewer modal and click **Download Report**
- **Admin CSV:** In the Admin Panel Stats tab, click **Export CSV**

---

## 6. Architecture Overview

### 6.1 Service Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────────────┐
│  Browser │────▶│  Nginx   │────▶│   API Service    │
│ :3050    │     │ :3050    │     │   :8000          │
└──────────┘     └──────────┘     └──────┬───────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
             ┌──────────┐        ┌──────────────┐    ┌──────────────┐
             │  Redis   │        │ PostgreSQL   │    │  Prometheus  │
             │  :6379   │        │  :5432       │    │  :9090       │
             └────┬─────┘        └──────────────┘    └──────┬───────┘
                  │                                         │
                  ▼                                         ▼
          ┌──────────────┐                          ┌──────────────┐
          │   Worker(s)  │                          │   Grafana    │
          │   :8001      │                          │   :3000      │
          └──────────────┘                          └──────────────┘
                  ▲
                  │
          ┌──────────────┐
          │  Autoscaler  │
          │  :8002       │
          └──────────────┘
```

### 6.2 Data Flow (Plagiarism Detection Pipeline)

```
1. User uploads file → API validates (size, type, magic bytes)
2. API stores file → enqueues job in Redis
3. Worker picks up job → extracts text (PDF/DOCX/txt)
4. Worker runs AI detection (RoBERTa + DistilGPT2 + stylometry)
5. Worker computes similarity matrix (TF-IDF + SBERT hybrid, alpha=0.5)
6. Results stored in Redis + PostgreSQL
7. API notifies frontend via WebSocket
8. Frontend displays matrix, collusion graph, AI badges
```

### 6.3 Self-Healing Mechanisms

| Mechanism | Interval | Description |
|---|---|---|
| `_monitor_db()` | Every 30s | Retries DB connection if unavailable |
| `_recover_stale_jobs()` | Every 60s | Fixes DB-FAILED/Redis-PROCESSING mismatches |
| Job retry | Up to 3× | Failed jobs re-enqueued with backoff before dead letter |
| `_drain_dead_letter()` | Every 60s | Re-queues dead-letter jobs under max retries |
| Alertmanager webhook | — | Auto-remediation counters for Prometheus alerts |
| Dependency-aware `/health` | On request | Returns `degraded` if Redis or DB is down |

### 6.4 Key Technical Decisions

| Area | Decision | Rationale |
|---|---|---|
| **Similarity** | TF-IDF + SBERT hybrid (alpha=0.5) | Lexical + semantic coverage |
| **AI Detection** | 50% RoBERTa + 30% PPL/Burst + 20% Stylo | Multi-signal robustness |
| **Auth** | httpOnly cookies (primary) + localStorage (fallback) | Security + local demo convenience |
| **Queue** | Redis (sync in worker, async in API) | Appropriate for blocking vs event-loop |
| **Autoscaler** | In-container Docker SDK | No host dependencies |
| **WebSocket** | Redis Pub/Sub for multi-replica | Scales to multiple API instances |

---

## 7. Key Features to Show

When presenting to teachers, this is the recommended feature tour:

| # | Feature | Where | What to Show |
|---|---|---|---|
| 1 | **Student Upload** | `/student` | No-login submission with access code |
| 2 | **Dashboard** | `/dashboard` | Assignment management, owned/shared lists |
| 3 | **Similarity Matrix** | Dashboard detail | Color-coded grid, cell click → side-by-side |
| 4 | **AI Detection** | Dashboard rows | Green/yellow/red badges per submission |
| 5 | **Collusion Graph** | Dashboard detail | Network graph of highly-similar submissions |
| 6 | **Blind Review** | Dashboard toggle | Anonymised labels with one click |
| 7 | **Cross-Batch Comparison** | `/cross-batch` | Compare submissions across assignments |
| 8 | **Student Dashboard** | `/student/dashboard` | Student view of own submissions |
| 9 | **Admin Panel** | `/admin` | Stats, user management, audit log |
| 10 | **PDF Report** | Matrix Viewer | Downloadable pairwise similarity report |
| 11 | **CSV Export** | Dashboard | Bulk export for offline analysis |
| 12 | **Monitoring** | `:8090` | Live service health, metrics |
| 13 | **Grafana** | `:3000` | Pre-provisioned dashboards |
| 14 | **Dark Mode** | Navbar toggle | Accessibility / preference |

---

## 8. Troubleshooting

### 8.1 Worker Build Takes Too Long

The worker Docker build downloads ~3 GB of ML models (PyTorch, SBERT, RoBERTa, DistilGPT2).

| Problem | Solution |
|---|---|
| First build >30 min | Expected. Subsequent builds reuse Docker layer cache. |
| Build fails with timeout | Ensure stable internet. Set `DOCKER_BUILDKIT=1` for better cache. |
| Build disk full | Run `docker system prune -af` to free space. |

### 8.2 Container Won't Start

```bash
# Check container logs
docker compose logs <service-name>

# Common issues:
# - Port already in use → change host port in docker-compose.yml
# - Docker not running → start Docker Desktop / daemon
# - Out of memory → increase Docker RAM limit in settings
```

### 8.3 "No similarity data" on Dashboard

| Cause | Fix |
|---|---|
| <2 submissions uploaded | Upload more files |
| Compute not run yet | Click **Compute similarity** |
| Compute still running | Wait for progress bar to complete |
| Job failed | Check worker logs: `docker compose logs worker` |
| Worker still loading models | Wait 30–60s after startup |

### 8.4 Login / Auth Issues

```bash
# Direct DB access to check users
docker compose exec postgres psql -U plagio -d plagioscale -c "SELECT email, role FROM users;"

# Reset a user's password (via API — no direct password reset endpoint yet)
# Log in via the frontend and use "Forgot password" flow
```

### 8.5 Reset Everything

```bash
# Stop and remove all containers, volumes, and images
docker compose down -v
docker system prune -af --volumes

# Rebuild from scratch
docker compose up -d --build
```

---

## 9. Appendix: Service Reference

### 9.1 All Docker Services

| Service | Image | Port(s) | Health Check | Mem Limit |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | pg_isready | 256 MB |
| `redis` | `redis:7-alpine` | 6379 | redis-cli ping | 128 MB |
| `api-service` | Custom | 8000, 8443 | HTTP /health | 256 MB |
| `worker` | Custom | — | HTTP :8001 | 2048 MB |
| `frontend` | Custom (Nginx) | 3050 | nginx -t | 128 MB |
| `autoscaler` | Custom | 8002 | HTTP /metrics | 128 MB |
| `monitoring-service` | Custom | 8090 | HTTP /health | 128 MB |
| `prometheus` | `prom/prometheus` | 9090 | wget /-/healthy | 256 MB |
| `alertmanager` | `prom/alertmanager` | 9093 | wget /-/healthy | 64 MB |
| `grafana` | `grafana/grafana:9.0.0` | 3000 | HTTP /api/health | 256 MB |

### 9.2 Key File Paths

| Path | Purpose |
|---|---|
| `docker-compose.yml` | All service definitions |
| `.env.example` → `.env` | Environment configuration |
| `shared/` | Shared Python modules (database, models, queue, ML pipeline) |
| `api-service/main.py` | FastAPI app |
| `worker-service/worker.py` | Background job processor |
| `frontend/src/` | React source code |
| `prometheus/` | Prometheus config + alerts |
| `grafana/provisioning/` | Pre-configured dashboards |
| `scripts/seed_test_data.py` | Demo data generator |

### 9.3 Useful Docker Commands

```bash
# View real-time logs
docker compose logs -f api-service
docker compose logs -f worker

# Execute commands inside a running container
docker compose exec postgres psql -U plagio -d plagioscale
docker compose exec api-service python -c "import shared; print(shared.__file__)"

# Scale workers (autoscaler does this automatically, but manual for testing)
docker compose up -d --scale worker=3 --no-recreate

# Check resource usage
docker stats

# Rebuild a single service without cache
docker compose build --no-cache worker
```

### 9.4 Network Architecture

All services communicate over the internal `plagioscale-network` bridge network. External access is via published ports only:

- Frontend → API: via `VITE_API_BASE` env var (`http://localhost:8000`)
- Worker → DB/Redis: via internal hostnames (`postgres:5432`, `redis:6379`)
- Autoscaler → Docker socket: via mounted `/var/run/docker.sock`
- Monitoring → Docker socket: via mounted `/var/run/docker.sock`
