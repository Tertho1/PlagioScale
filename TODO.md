# PlagioScale — TODO

> Cross-agent task tracking. Updated per project_plan.md audit (July 2026).

## Legend

| Icon | Meaning |
|------|---------|
| ✅ | Done |
| 🚧 | In progress |
| ❌ | Not started |
| 🔜 | Planned |

---

## Phase 0 — Foundation (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 0.1 | CI skeleton `.github/workflows/ci.yml` | ✅ | Exists, but CI gap still open (covered in Round 3) |
| 0.2 | pytest.ini | ✅ | |
| 0.3–0.5 | Unit tests (PlagiarismDetector, TextVectorizer, QueueClient) | ✅ | 35 tests |
| 0.6 | ruff + `.pre-commit-config.yaml` | ✅ | |
| 0.7–0.8 | docker-compose hardening (resource limits + health checks) | ✅ | |
| 0.9 | Folder restructure | ✅ | Executed per plan |
| 0.10 | `.gitignore` update | ✅ | |

## Phase 1 — Security (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 1.1–1.10 | JWT exp, filename sanitization, magic bytes, upload limit, rate limiting, fail-safe secret, `datetime` fixes, `except`→logging, redis volume, `password_hash` removal | ✅ | All 10 tasks done |

## Phase 2 — Core Stabilization (⚠️ 10/12 done)

| # | Task | Status | Notes |
|---|---|---|---|
| 2.1–2.6 | TF-IDF, clamp [0,1], fallback fix, atomic `create_submission`, async Redis, WS cleanup | ✅ | |
| 2.7 | Delete host autoscaler, keep in-container only | ❌ | `infrastructure/host_autoscaler.py` + `run_autoscaler.ps1` still exist → **Round 2** |
| 2.8–2.9 | worker_id label, worker storage volume | ✅ | |
| 2.10 | Remove `container_name` from scalable services | ❌ | 9 of 10 services have it → **Round 2** |
| 2.11–2.12 | Pagination, pg_backup.sh | ✅ | |

## Phase 3 — Frontend UX (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 3.1–3.6 | WebSocket, MatrixViewer, error surfacing, student dashboard, CSS, JWT refresh | ✅ | |

## Phase 4 — Advanced Features (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 4.1–4.3 | Collusion graph, blind review, CSV enhanced | ✅ | |

## Phase 5 — Integration Tests (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 5.1–5.5 | API/worker/frontend tests, stress test update, seed data | ✅ | 54 Python + 10 frontend tests |

## Phase 6 — Documentation (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 6.1–6.5 | PROGRESS.md, README.md, AGENTS.md, docs archive, root cleanup | ✅ | |

---

## Remaining Work — 4 Rounds

### Round 1 — Fix Critical Bugs (blocking student flow) ✅

| # | Bug | Priority | Files | Status |
|---|---|---|---|---|
| R1.1 | `get_user_by_email` missing `password_hash` → login broken for all users | 🔴 HIGH | `shared/database.py` | ✅ Added `password_hash` to returned dict |
| R1.2 | `create_assignment` returns success even if DB write silently fails | 🟠 MEDIUM | `api-service/main.py` | ✅ Check `db_create_assignment` return value, raise 500 on failure |
| R1.3 | `StudentDashboard.jsx` upload missing required `roll` field → 422 error | 🟠 MEDIUM | `frontend/src/pages/StudentDashboard.jsx` | ✅ Added roll + name inputs and FormData appends |

### Round 2 — Unblock Autoscaling (Phase 2.7 + 2.10 leftovers) ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R2.1 | Delete `infrastructure/host_autoscaler.py` + `run_autoscaler.ps1` | 🔴 HIGH | `infrastructure/` | ✅ Removing host variant — keeping only in-container autoscaler/ |
| R2.2 | Remove `container_name` from scalable services (`api-service`, `frontend`) | 🔴 HIGH | `docker-compose.yml` | ✅ Removed from `api-service` and `frontend` (worker had none) |
| R2.3 | Replace hardcoded `WORKER_ID=worker-1` with `socket.gethostname()` fallback | 🟠 MEDIUM | `worker-service/worker.py` | ✅ Dynamic via `os.getenv('WORKER_ID') or socket.gethostname()` |
| R2.4 | Add autoscaler tests (23 unit tests, mocked Docker/Redis/Prometheus) | 🟢 LOW | `autoscaler/tests/test_autoscaler.py` | ✅ + `pytest.ini` updated to include `autoscaler/tests` |

### Round 3 — Polish & CI

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R3.1 | Update CI to filter integration tests (`-m "not integration"`), run all 3 test dirs + frontend tests | 🟠 MEDIUM | `.github/workflows/ci.yml` | ✅ Already done — all test dirs, `-m "not integration"`, and frontend tests covered |
| R3.2 | Ensure CI job names reflect true test coverage | 🟢 LOW | `.github/workflows/ci.yml` | ❌ (optional rename) |

### Round 4 — E2E & Load ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R4.1 | Create full-stack E2E test (create assignment → upload → compute → matrix) | 🟢 LOW | `tests/e2e/test_pipeline.py` | ✅ 3 tests: health, full pipeline, anonymous flow. Marked `@pytest.mark.e2e` |
| R4.2 | Update stress test with scaled worker verification | 🟢 LOW | `scripts/stress_test.py` | ✅ Added `--scale N` flag for pre-scaling workers |

---

See `docs/project_plan.md` for full roadmap.
See `PROGRESS.md` for detailed progress by component.
