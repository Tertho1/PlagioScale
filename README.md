# PlagioScale

Cloud-native, microservices-based plagiarism detection platform.
Runs entirely locally via Docker Compose — no cloud services or paid APIs.

```
API (FastAPI, port 8000) → Redis Queue → Worker(s) (port 8001) → PostgreSQL
     ↕                                      ↕
Frontend (React/Vite, port 3050)    Autoscaler (port 8002)
     ↕
Monitoring (FastAPI, port 8090) → Prometheus → Grafana
```

---

## Quick Start (Docker)

```bash
docker compose up -d --build
```

This starts all 7 services:

| Service | Port | Purpose |
|---|---|---|
| `api-service` | 8000 | REST API — submissions, auth, batch management, CSV export |
| `worker-service` | — | Background job processor (plagiarism detection pipeline) |
| `autoscaler` | 8002 | In-container autoscaler (Docker SDK) |
| `monitoring-service` | 8090 | Live HTML dashboard + WebSocket metrics |
| `frontend` (Nginx) | 3050 | React SPA served via Nginx |
| `postgres` | 5432 | Primary database |
| `redis` | 6379 | Job queue + metadata store |
| `prometheus` | 9090 | Metrics scraping |
| `grafana` | 3000 | Dashboards (admin/admin) |

### Smoke test

1. Open http://localhost:3050
2. Sign up as teacher → create an assignment
3. Upload ≥2 submissions via the student portal
4. Click **Compute similarity** on the dashboard
5. View the similarity matrix, collusion graph, or export CSV
6. Toggle **Blind Review** to anonymise submission labels

---

## Architecture

### Services

| Service | Stack | Dependencies |
|---|---|---|
| `api-service/` | FastAPI, SQLAlchemy, Redis (async) | Postgres, Redis |
| `worker-service/` | Python, scikit-learn, pypdf, python-docx | Redis, Postgres (optional) |
| `autoscaler/` | FastAPI, Docker SDK | Docker socket |
| `monitoring-service/` | FastAPI, Prometheus client, psutil | Redis |
| `frontend/` | React 18, Vite, react-force-graph-2d | API |
| `shared/` | Common models, queue client, vectorizer, text extraction | — |

### Plagiarism pipeline

```
Submit text/file → API validates → enqueue job in Redis
  → Worker dequeues → extract text (PDF/DOCX/txt)
  → TF-IDF vectorize → compare_with_database (cosine similarity)
  → Store result in Redis + DB → notify API
```

### Key design decisions

| Decision | Detail |
|---|---|
| **Async Redis in API** | `AsyncQueueClient` in `shared/queue_client.py` — non-blocking Redis for the FastAPI event loop |
| **Sync Redis in Worker** | `QueueClient` — synchronous Redis for the blocking worker process |
| **Text extraction** | `shared/text_extraction.py` — lazy imports for PDF/DOCX/txt to avoid runtime deps in the API |
| **Autoscaler** | Two variants: in-container (Docker SDK, preferred) + host subprocess (fallback in `scripts/host_autoscaler.py`) |
| **JWT auth** | localStorage-based (XSS-vulnerable, acceptable for local demo). Auto-refresh with 5-min expiry margin |
| **Rate limiting** | slowapi: `/submit` 30/min, `/auth/signup` 10/min, `/auth/login` 20/min, `/portal/submit` 60/min |
| **File uploads** | Sanitised filenames, extension whitelist + magic-byte check, 10 MB limit |
| **WebSocket** | Single API instance only — no Redis Pub/Sub for multi-replica yet. Stale connections cleaned every 30s |

---

## Local Development

### Python backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirementsall.txt
```

You'll need Redis and PostgreSQL running locally, with appropriate env vars set.

### Frontend

```bash
cd frontend
npm install
npm run dev      # port 5173, proxies /api → http://localhost:8000
npm run build    # production build → frontend/dist
npm run test     # Vitest (10 tests)
```

### Tests

```bash
# Shared unit tests (35 tests)
python -m pytest shared/tests -v

# API integration tests (12 tests, mocked deps)
python -m pytest api-service/tests -v

# Worker integration tests (7 tests, mocked deps)
python -m pytest worker-service/tests -v

# All Python tests
python -m pytest api-service/tests worker-service/tests shared/tests -v

# Frontend tests
cd frontend && npx vitest run

# Lint
ruff check .
```

All tests pass on Python 3.14 with mocked dependencies.

### Seed data

```bash
python scripts/seed_test_data.py                    # 2 batches, 5 students each
python scripts/seed_test_data.py --batches 3 --students 10
```

### Stress testing

```bash
python scripts/stress_test.py 20 5   # 20 jobs, 5 concurrent threads
```

Includes pre/post autoscaler state comparison.

---

## Environment Variables

| Variable | Default | Service |
|---|---|---|
| `DB_HOST` | `postgres` | API, Worker |
| `DB_USER` | `plagioscale` | API, Worker |
| `DB_PASSWORD` | `plagioscale` | API, Worker |
| `DB_NAME` | `plagioscale` | API, Worker |
| `REDIS_HOST` | `redis` | API, Worker, Autoscaler |
| `JWT_SECRET` | `please-change-this-secret` | API |
| `ENV` | `development` | API (fails fast in `production` with default secret) |
| `VITE_API_BASE` | `http://localhost:8000` | Frontend |
| `WORKER_ID` | `worker-default` | Worker |

---

## Project structure

```
api-service/          FastAPI REST API (port 8000)
worker-service/       Background job processor
autoscaler/           In-container autoscaler (port 8002)
monitoring-service/   Live monitoring dashboard (port 8090)
shared/               Python modules (models, queue, vectorizer, plagiarism, text extraction)
frontend/             React + Vite + Nginx (port 3050)
scripts/              Utility scripts (stress test, seed data, autoscaler)
prometheus/           Prometheus scrape config
grafana/              Pre-provisioned dashboards
```

## API endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | — | Health check |
| `/metrics` | GET | — | Prometheus metrics |
| `/submit` | POST | — | Submit text for plagiarism check |
| `/result/{id}` | GET | — | Get job result |
| `/status/{id}` | GET | — | Get job status |
| `/queue/stats` | GET | — | Queue length |
| `/auth/signup` | POST | — | Create account |
| `/auth/login` | POST | — | Login |
| `/auth/refresh` | POST | Bearer | Refresh JWT |
| `/portal/submit` | POST | Bearer | Upload file submission |
| `/portal/batches` | GET | Bearer | List batches |
| `/portal/assignments` | GET | Bearer | List assignments |
| `/portal/submissions/{batch_id}` | GET | Bearer | List submissions (paginated) |
| `/portal/submissions/{batch_id}/{sub_id}/text` | GET | Bearer | Get extracted text |
| `/portal/compute/{batch_id}` | POST | Bearer | Trigger similarity computation |
| `/portal/matrix/{batch_id}` | GET | Bearer | Get similarity matrix |
| `/portal/export/{batch_id}` | GET | Bearer | Download CSV (roll, name, email, submission_id, filename, scores) |
| `/ws` | — | — | WebSocket (progress updates) |

---

## What's changed

See `TODO.md` for per-task tracking and `AGENTS.md` for agent context.

Key recent additions:
- **Phase 4** — Collusion graph, blind review mode, CSV enhanced columns
- **Phase 5** — 54 Python tests (12 API + 7 worker + 35 shared), 10 frontend tests, seed data script, stress test with autoscaling verification
- JWT refresh mechanism, rate limiting, file upload validation
- Matched similarity matrix with row/column order for collusion graph
- `hash_password()` error handling for passlib/bcrypt compatibility

---

## License

Provided as-is for educational and demonstration purposes.
