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

> **Full setup guide with prerequisites, walkthrough, and troubleshooting:** [docs/setup_guide.md](docs/setup_guide.md)
> 
> For a comprehensive demo script showing every feature in order, see §5 — Demo Walkthrough in the setup guide.

This starts all services:

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
| `shared/` | Common models, queue client, vectorizer, text extraction, AI detector, OCR, PDF reports, email notifier, external lookup, audit log | — |

### Plagiarism pipeline

```
Submit text/file → API validates → enqueue job in Redis
  → Worker dequeues → extract text (PDF/DOCX/txt)
  → Hybrid similarity: TF-IDF (lexical) + SBERT (semantic)
  → AI content detection (RoBERTa + DistilGPT2 + stylometric features)
  → Store result in Redis + DB → notify API
```

### Key design decisions

| Decision | Detail |
|---|---|
| **Async Redis in API** | `AsyncQueueClient` in `shared/queue_client.py` — non-blocking Redis for the FastAPI event loop |
| **Sync Redis in Worker** | `QueueClient` — synchronous Redis for the blocking worker process |
| **Text extraction** | `shared/text_extraction.py` — lazy imports for PDF/DOCX/txt to avoid runtime deps in the API |
| **Autoscaler** | In-container (Docker SDK) — host variant removed |
| **JWT auth** | httpOnly cookies + CSRF (primary), localStorage fallback for JS access. Session invalidation on role change via `token_version` |
| **Rate limiting** | slowapi + WS rate limit (10/min per IP) |
| **File uploads** | Sanitised filenames, extension whitelist + magic-byte check, 10 MB limit |
| **WebSocket** | Multi-replica via Redis Pub/Sub (`ws:progress` channel). Stale connections cleaned every 30s |
| **Dark mode** | CSS variables + `[data-theme]` + localStorage persistence — toggle in navbar |
| **mTLS** | Optional `USE_MTLS=true` — auto-generated certs in `certs/`, uvicorn SSL, worker client certs |
| **Auth** | JWT (httpOnly cookies + CSRF primary, localStorage fallback). Session invalidation on role change via `token_version` |
| **Non-root containers** | api-service, worker-service run as UID 1000 |

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
npm run test     # Vitest (30 tests)
```

### Tests

```bash
# Shared unit tests
python -m pytest shared/tests -v

# API integration tests
python -m pytest api-service/tests -v

# Worker integration tests
python -m pytest worker-service/tests -v

# All Python tests
python -m pytest api-service/tests worker-service/tests shared/tests -v

# Frontend tests
cd frontend && npx vitest run

# Lint
ruff check .
```

All tests pass on Python 3.14 with mocked dependencies (130 Python + 30 frontend = 160 total).


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
shared/               Python modules (models, queue, vectorizer, plagiarism, text extraction,
                      AI detector, OCR, PDF reports, email notifier, external lookup, audit log)
frontend/             React + Vite + Nginx (port 3050)
tests/                End-to-end pipeline tests
alembic/              Database migrations
certs/                TLS certs (regenerate with: python certs/generate.py)
scripts/              Utility scripts (stress test, seed data, autoscaler, deploy)
docs/                 Planning docs + setup guide
prometheus/           Prometheus scrape config + alerts + alertmanager config
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
| `/auth/logout` | POST | — | Logout (invalidate session) |
| `/auth/csrf-token` | GET | — | Get CSRF token |
| `/auth/me` | GET | Bearer | Get current user profile |
| `/portal/submit` | POST | Bearer | Upload file submission |
| `/portal/batches` | GET | Bearer | List batches |
| `/portal/assignments` | GET | Bearer | List assignments |
| `/portal/assignments` | POST | Bearer | Create assignment |
| `/portal/assignments/{batch_id}` | GET | Bearer | Get assignment detail |
| `/portal/assignments/{batch_id}` | PUT | Bearer | Update assignment settings |
| `/portal/assignments/{batch_id}` | DELETE | Bearer | Delete assignment |
| `/portal/submissions/{batch_id}` | GET | Bearer | List submissions (paginated) |
| `/portal/submissions/{batch_id}/{submission_id}/text` | GET | Bearer | Get extracted text |
| `/portal/submissions/{submission_id}/cancel` | POST | Bearer | Cancel a submission |
| `/portal/compute-similarity/{batch_id}` | POST | Bearer | Trigger similarity computation |
| `/portal/similarity-matrix/{batch_id}` | GET | Bearer | Get similarity matrix |
| `/portal/report/{batch_id}/{sub_id_1}/{sub_id_2}` | GET | Bearer | Download PDF similarity report |
| `/portal/cross-batch/{batch_id_1}/{batch_id_2}` | GET | Bearer | Compare submissions across two batches |
| `/portal/student-comparison/{submission_id}` | GET | Bearer | All pairwise scores for one student |
| `/portal/self-check` | POST | Bearer | Student draft self-check |
| `/portal/annotations/{submission_id}` | GET/POST | Bearer | Get/post instructor annotations |
| `/portal/annotations/{annotation_id}` | DELETE | Bearer | Delete annotation |
| `/portal/external-lookup/{submission_id}` | POST | Bearer | Simulated web/academic phrase search |
| `/portal/notify` | POST | Bearer | Trigger email notifications for a batch |
| `/portal/notify-email/{submission_id}` | POST | Bearer | Send notification for one submission |
| `/portal/my` | GET | Bearer | Get current user's submissions |
| `/admin/stats` | GET | Admin | System-wide statistics |
| `/admin/stats/export` | GET | Admin | Download stats as CSV |
| `/admin/users` | GET | Admin | List users (search, paginated) |
| `/admin/users/{user_id}/role` | POST | Admin | Change user role |
| `/admin/notifications/send` | POST | Admin | Send pending email notifications |
| `/admin/audit/tail` | GET | Admin | SSE stream of audit log entries |
| `/api/webhooks/alertmanager` | POST | — | Alertmanager webhook for auto-remediation |
| `/ws` | — | — | WebSocket (progress updates, multi-replica via Redis Pub/Sub) |

---

## What's changed

See `TODO.md` for per-task tracking and `AGENTS.md` for agent context (including branch strategy and work rules).

Key recent additions:
- **Round 22** — Post-push UI bug fixes (login flow, roll fallback, access code copy)
- **Round 21** — UI accessibility (similarity bands, badge semantics, theme flash prevention, cookie-auth on submit, live smoke 17/17)
- **Round 20** — Security depth, worker reliability, frontend polish (role hierarchy, HMAC CSRF, signup enumeration, AI detect timeout, fire-and-forget notifications)
- **Round 19** — Bug fixes, security hardening, performance (SBERT batching, vectorized cosine, DB pool sizing, ErrorBoundary, lazy CollusionGraph)
- **Round 18** — Feature additions (similarity bands, threshold filter, in-document highlights, AI confidence labels, student self-check, assignment settings, side-by-side comparison, batch analytics, empty states, annotation layer)
- **Round 17** — Security audit remediation (ownership checks, access code hiding, CSRF on mutations)
- **Round 16** — Refactoring & frontend improvements (auth guards, React.lazy, skeleton loading, WS retry)
- **Round 15** — Similarity compute + AI detection stability (HF cache, stale job recovery, retry limits)
- **Round 13** — Session invalidation, WS rate limiting, CSV export, admin search/pagination, non-root containers, dark mode, live audit log, multi-replica WebSocket, mTLS, 54 unit tests
- **Phase 4** — Collusion graph, blind review mode, CSV enhanced columns
- **Phase 5** — 160 tests total, seed data script, stress test with autoscaling verification

---

## License

Provided as-is for educational and demonstration purposes.
