# PlagioScale — Final Project Plan (Local Docker Edition)

> **Budget:** $0 — no cloud services, no paid APIs, everything runs locally in Docker.
> **Based on:** `PlagioScale_Proposal_FreeTier.md` (original AWS free-tier vision), `project_plan_reworked.md` (intermediate local plan), and the current codebase analysis.

---

## 1. What Exists vs. What Was Proposed

| Feature | AWS Proposal | Intermediate Plan | Current Codebase | Status |
|---|---|---|---|---|
| Compute | EC2 t2.micro | Docker Compose | Docker Compose | Done |
| Queue | SQS | Redis Queue | Redis Queue | Done |
| Database | RDS / SQLite | PostgreSQL | PostgreSQL | Done |
| Cache | Redis (Docker) | Redis | Redis (no volume mount!) | Needs fix |
| Auth | Cognito | JWT + localStorage | JWT + localStorage | Done |
| Storage | S3 | Named Volumes | Named Volumes | Done |
| AI Detection | HuggingFace API | sklearn/transformers | sklearn TF-IDF | Done |
| Plagiarism | k-shingle | k-shingle | k-shingle + cosine | Done |
| Monitoring | CloudWatch | Custom API | Prometheus + Grafana + Monitoring API | Done |
| CDN/Gateway | S3 Static / Nginx | Nginx | Nginx (frontend container) | Done |
| Worker Autoscaling | Custom Autoscaler | `docker compose --scale` | 2 implementations (in-container + host) | Needs fix |
| WebSocket real-time | — | Redis Pub/Sub + WS | WS endpoint exists (frontend never connects) | Needs work |
| Collusion Graph | — | react-force-graph | Not implemented | Todo |
| Blind Review Mode | — | Toggle | Not implemented | Todo |
| Student Dashboard | — | Auth-scoped views | Basic, not scoped per student | Needs work |
| CI/CD | GitHub Actions | GitHub Actions | Not implemented | Todo |
| K3s/K8s | K3s on EC2 | — | Not implemented | Deferred |
| Testing | — | — | Ad-hoc scripts only | Todo |

---

## 2. Revised Folder Structure

```
D:\Projects\PlagioScale\
├── api-service/
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       ├── test_routes.py
│       ├── test_auth.py
│       └── test_uploads.py
├── worker-service/
│   ├── worker.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       ├── test_worker.py
│       └── test_extraction.py
├── autoscaler/
│   ├── autoscaler.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       └── test_autoscaler.py
├── monitoring-service/
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── shared/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   ├── queue_client.py
│   ├── plagiarism.py
│   ├── vectorizer.py
│   └── tests/
│       ├── test_plagiarism.py
│       ├── test_vectorizer.py
│       └── test_queue.py
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── pages/
│   │   │   ├── AuthPage.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── StudentSubmit.jsx
│   │   │   ├── StudentDashboard.jsx      # NEW — scoped per student
│   │   │   └── CollusionGraph.jsx        # NEW
│   │   ├── components/
│   │   │   ├── Dropzone.jsx
│   │   │   ├── SimilarityMatrix.jsx
│   │   │   ├── MatrixViewer.jsx
│   │   │   └── BlindReviewToggle.jsx     # NEW
│   │   ├── utils/
│   │   │   ├── auth.js
│   │   │   └── websocket.js              # NEW
│   │   └── styles/
│   │       └── portal.css
│   ├── package.json
│   ├── vite.config.js
│   ├── nginx.conf
│   ├── Dockerfile
│   └── tests/
│       ├── setup.js
│       └── components/
├── scripts/
│   ├── demo_scale.py
│   ├── scale_workers.ps1
│   ├── stress_test.py                    # moved from root
│   ├── seed_test_data.py                 # NEW
│   └── pg_backup.sh                      # NEW — simple pg_dump wrapper
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   ├── dashboards/
│   └── provisioning/
├── docs/                                 # archive of historical documents
│   ├── ELASTICITY_DEMO_REPORT.md
│   └── PlagioScale_Proposal_FreeTier.md
├── .github/
│   └── workflows/
│       └── ci.yml                        # NEW
├── docker-compose.yml
├── requirementsall.txt
├── pytest.ini                            # NEW
├── .env.example                          # NEW
├── .pre-commit-config.yaml               # NEW
├── AGENTS.md                             # NEW
└── README.md
```

---

## 3. Testing Strategy

```
tests/
├── unit/                   # Fast, isolated, no Docker
│   ├── test_plagiarism.py  # PlagiarismDetector.detect(), jaccard, cosine
│   ├── test_vectorizer.py  # TextVectorizer.add_document(), compute_similarity_matrix()
│   ├── test_queue.py       # QueueClient mock tests
│   └── test_models.py      # Job model serialization/deserialization
├── integration/            # Needs Redis + PostgreSQL (via Docker)
│   ├── test_api_routes.py  # FastAPI TestClient + real DB
│   ├── test_worker.py      # Full submit -> queue -> process -> result cycle
│   ├── test_extraction.py  # PDF/DOCX/txt extraction
│   └── test_auth.py        # Signup -> login -> JWT -> protected route
├── e2e/                    # Full stack (all containers running)
│   └── test_pipeline.py    # Create assignment -> upload -> compute -> matrix
└── load/                   # Performance
    └── test_stress.py      # 50+ concurrent jobs, verify autoscaling
```

**Tools:** pytest, pytest-asyncio, httpx, pytest-cov, React Testing Library, ruff (lint), slowapi (rate limit)

**CI pipeline (`.github/workflows/ci.yml`):**
```yaml
name: CI
on: [push, pull_request]
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirementsall.txt
      - run: pip install ruff pytest pytest-asyncio httpx
      - run: ruff check .                         # lint
      - run: pytest tests/unit/                   # unit tests (fast, no Docker)
      - run: |
          docker compose up -d redis postgres
          sleep 5
          pytest tests/integration/               # integration tests
```

---

## 4. Architectural Decisions

### 4.1 Autoscaler: Choose One

Two implementations exist. Keep **one**, delete the other:

| Variant | Mechanism | Portability | Decision |
|---|---|---|---|
| `autoscaler/autoscaler.py` | Docker SDK (in-container) | Requires docker.sock mount | **KEEP** — container-native, works anywhere Docker runs |
| `host_autoscaler.py` | Subprocess `docker compose` | Windows-specific, fragile | **DELETE** — move useful test config to the kept one |

Both achieve `docker compose up --scale worker=N` — the in-container variant does it through the Python Docker SDK instead of shelling out to `docker compose`. Same result, less fragile.

### 4.2 WebSocket Scaling Limit

`ws_connections` is an in-memory dict in the API process. If the API service is ever horizontally scaled, WebSocket state won't be shared across replicas. For the current single-container deployment this is fine. If scaling the API becomes necessary later, switch to **Redis Pub/Sub for WebSocket broadcast** (the worker already publishes to Redis; the API would subscribe per batch).

### 4.3 JWT Storage Decision

Tokens are stored in `localStorage` — this is XSS-vulnerable. Acceptable for a local demo project, but before any deployment-like use, switch to **httpOnly cookies**. The plan leaves `localStorage` for now but calls this out explicitly so it's a conscious tradeoff, not an oversight.

### 4.4 Resource Limits for Autoscaling

Without `mem_limit` and `cpus` in `docker-compose.yml`, worker containers can consume the entire host. This makes load-based autoscaling unrealistic (you'll never see real backpressure or cooldown behavior). **Add resource limits to all services** in Phase 0.

---

## 5. Revised Phase-by-Phase Implementation Plan

### Phase 0: Foundation — CI, Tests, and Harden Core (Week 1)

> **Rationale:** Everything after this lands on a verified, CI-checked base. No untested bug fixes, no untested features.

| # | Task | Priority | Files |
|---|---|---|---|
| 0.1 | CI skeleton: lint + unit tests on push | High | `.github/workflows/ci.yml` |
| 0.2 | Write unit tests for `PlagiarismDetector` | High | `shared/tests/test_plagiarism.py` |
| 0.3 | Write unit tests for `TextVectorizer` | High | `shared/tests/test_vectorizer.py` |
| 0.4 | Write unit tests for `QueueClient` | High | `shared/tests/test_queue.py` |
| 0.5 | Add `pytest.ini` with config | High | `pytest.ini` |
| 0.6 | Add `ruff` config and pre-commit hook | Medium | `.pre-commit-config.yaml` |
| 0.7 | Set resource limits (`mem_limit`, `cpus`) in `docker-compose.yml` | High | `docker-compose.yml` |
| 0.8 | Add health check dependencies to all services that need them | High | `docker-compose.yml` |
| 0.9 | Migration plan: move loose root scripts to `scripts/` | Low | `scripts/` |

### Phase 1: Fix Critical Bugs & Security Issues (Week 2)

| # | Task | Priority | Files |
|---|---|---|---|
| 1.1 | Add JWT expiration (`exp` claim) | High | `api-service/main.py:140-143` |
| 1.2 | Sanitize uploaded filenames | High | `api-service/main.py:443` |
| 1.3 | Validate file types via `python-magic` | High | `api-service/main.py:421`, add `python-magic` to requirements |
| 1.4 | Add max upload size limit | High | `api-service/main.py`, `docker-compose.yml` |
| 1.5 | Add rate limiting via `slowapi` | Medium | `api-service/main.py` |
| 1.6 | **Fail-fast** on default JWT secret when not in dev mode | Medium | `api-service/main.py` |
| 1.7 | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` | Medium | All files |
| 1.8 | Replace `except: pass` with at minimum `logging.warning` | Medium | All files |
| 1.9 | **Mount `redis-data` volume** (was #8, upgraded to High) | High | `docker-compose.yml` |
| 1.10 | Remove `password_hash` from user response dicts | Medium | `shared/database.py` |

### Phase 2: Stabilize Core Features + Autoscaling (Week 3)

| # | Task | Priority | Files |
|---|---|---|---|
| 2.1 | Normalize vectorizer similarity to [0,1] range (clamp negative) | High | `shared/vectorizer.py:96` |
| 2.2 | Replace raw TF with TF-IDF in `PlagiarismDetector.cosine_similarity` | High | `shared/plagiarism.py:45-68` |
| 2.3 | Fix fallback identity matrix in vectorizer (return empty / raise) | Medium | `shared/vectorizer.py:116-119` |
| 2.4 | Make `create_submission` atomic (DB unique constraint) | High | `shared/database.py:287-298` |
| 2.5 | Use async Redis driver (`redis.asyncio`) for FastAPI | High | `api-service/main.py`, `shared/queue_client.py` |
| 2.6 | Fix WebSocket connection memory leak (cleanup empty batch sets) | Medium | `api-service/main.py:59` |
| 2.7 | Pick ONE autoscaler, delete the other (keep `autoscaler/autoscaler.py`) | High | `host_autoscaler.py`, `run_autoscaler.ps1` |
| 2.8 | Add `worker_id` label to worker Prometheus metrics | Medium | `worker-service/worker.py` |
| 2.9 | Persist worker `/app/storage` as Docker volume | Medium | `docker-compose.yml` |
| 2.10 | Remove fixed `container_name` from scalable services | Medium | `docker-compose.yml` |
| 2.11 | Add pagination to submission-listing endpoints | Medium | `api-service/main.py` |
| 2.12 | Add simple `pg_dump` backup script to `scripts/` | Low | `scripts/pg_backup.sh` |

### Phase 3: Frontend UX & Real-Time Features (Week 4)

| # | Task | Priority | Files |
|---|---|---|---|
| 3.1 | Connect frontend to WebSocket for live matrix updates | High | `frontend/src/utils/websocket.js`, `Dashboard.jsx` |
| 3.2 | Populate MatrixViewer with actual submission text snippets | High | `Dashboard.jsx:345`, `MatrixViewer.jsx` |
| 3.3 | Show backend errors to users (not just `console.error`) | Medium | `Dashboard.jsx:134-136` |
| 3.4 | Add scoped student dashboard (own submission history) | Medium | `StudentDashboard.jsx` |
| 3.5 | Replace inline styles with CSS classes | Low | `main.jsx:58` |
| 3.6 | Implement JWT token refresh mechanism | Medium | `api-service/main.py`, `auth.js` |

### Phase 4: Advanced Features (Week 5)

| # | Task | Priority | Files |
|---|---|---|---|
| 4.1 | Collusion Graph (react-force-graph) | Low | `CollusionGraph.jsx`, `package.json` |
| 4.2 | Blind Review Mode toggle | Low | `BlindReviewToggle.jsx`, `Dashboard.jsx` |
| 4.3 | Polish CSV Export | Low | `api-service/main.py:609-675` |

### Phase 5: Integration Tests & Load (Week 6)

| # | Task | Priority | Files |
|---|---|---|---|
| 5.1 | API integration tests (FastAPI TestClient + real DB) | Medium | `api-service/tests/test_routes.py` |
| 5.2 | Worker integration tests (full submit->queue->process->result) | Medium | `worker-service/tests/test_worker.py` |
| 5.3 | Frontend component tests (React Testing Library) | Low | `frontend/tests/` |
| 5.4 | Update stress test with autoscaling verification | Medium | `scripts/stress_test.py` |
| 5.5 | Seed data script for demo setup | Low | `scripts/seed_test_data.py` |

### Phase 6: Documentation & Polish (Week 7)

| # | Task | Priority | Files |
|---|---|---|---|
| 6.1 | Update PROGRESS.md to match actual codebase | Medium | `PROGRESS.md` |
| 6.2 | Update README.md with architecture diagram | Medium | `README.md` |
| 6.3 | Add AGENTS.md for AI-assisted development context | Low | `AGENTS.md` |
| 6.4 | Move historical docs to `docs/` | Low | `docs/` |
| 6.5 | Remove one-time diagnostic scripts from root | Low | Root cleanup |

---

## 6. Key Technical Debt Items

| Issue | Phase | Fix |
|---|---|---|
| Auto-expire old `ws_connections` entries | 2 | Add periodic cleanup or weak references |
| Embedding similarity returns [-1,1] not [0,1] | 2 | Clamp: `max(0, score)` |
| Fallback identity matrix (cosine path) is deceptive | 2 | Return empty matrix or raise instead |
| Raw TF instead of TF-IDF in `PlagiarismDetector` | 2 | Use sklearn's `TfidfVectorizer` consistently |
| Two autoscaler implementations (dead weight) | 2 | Pick one, delete the other |
| No pagination on submission listing | 2 | Add limit/offset parameters |
| No `__init__.py` in test packages | 0 | Add empty files |
| `diagnostic_and_fix.py` hardcodes `batch_id` | 6 | Remove (one-time script) |

---

## 7. Zero-Cost Guarantee Checklist

- No AWS, GCP, or Azure services used
- All databases self-hosted in Docker (PostgreSQL, Redis)
- All ML inference local (sklearn TF-IDF, no HuggingFace/OpenAI API fees)
- Frontend served via Nginx from Docker container
- Monitoring via self-hosted Prometheus + Grafana
- CI/CD via GitHub Actions free tier (2000 min/month)
- Docker image registry via public Docker Hub or GitHub Container Registry (free)
- Rate limiting via `slowapi` (free, FastAPI-native, no gateway fees)
- File validation via `python-magic` (free library, no SaaS)

---

## 8. Files to Archive or Remove

| File | Phase | Action | Reason |
|---|---|---|---|
| `PlagioScale_Proposal_FreeTier.md` | 6 | Archive to `docs/` | Superseded by actual codebase |
| `diagnostic_and_fix.py` | 6 | Remove | One-time use, hardcoded IDs, not reusable |
| `test_imports.py` | 6 | Remove | Redundant with pytest |
| `test_similarity_pipeline.py` | 6 | Remove | Replace with proper integration tests |
| `local_test_extraction.py` | 6 | Remove | Replace with proper integration tests |
| `ELASTICITY_DEMO_REPORT.md` | 6 | Archive to `docs/` | Historical record |
| `PlagioScale.7z` | 6 | Remove | Not needed in repo |
| `host_autoscaler.py` | 2 | Remove | Superseded by in-container autoscaler |
| `run_autoscaler.ps1` | 2 | Remove | Superseded by in-container autoscaler |
