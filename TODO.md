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
| 0.1 | CI skeleton `.github/workflows/ci.yml` | ✅ | Runs 4 pytest groups + frontend lint/build/test — 108 tests total |
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

## Phase 2 — Core Stabilization (✅ Complete)

| # | Task | Status | Notes |
|---|---|---|---|
| 2.1–2.6 | TF-IDF, clamp [0,1], fallback fix, atomic `create_submission`, async Redis, WS cleanup | ✅ | |
| 2.7 | Delete host autoscaler, keep in-container only | ✅ | `infrastructure/` deleted in Round 13 cleanup |
| 2.8–2.9 | worker_id label, worker storage volume | ✅ | |
| 2.10 | Remove `container_name` from scalable services | ✅ | Removed from api-service and frontend |
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
| R3.2 | Ensure CI job names reflect true test coverage | 🟢 LOW | `.github/workflows/ci.yml` | ✅ Renamed to `lint-and-test` + `frontend` per current matrix

### Round 4 — E2E & Load ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R4.1 | Create full-stack E2E test (create assignment → upload → compute → matrix) | 🟢 LOW | `tests/e2e/test_pipeline.py` | ✅ 3 tests: health, full pipeline, anonymous flow. Marked `@pytest.mark.e2e` |
| R4.2 | Update stress test with scaled worker verification | 🟢 LOW | `scripts/stress_test.py` | ✅ Added `--scale N` flag for pre-scaling workers |

### Round 5 — Compute & UI Polish ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R5.1 | `init_db()` returns `False` on migration failure → worker never queries DB | 🔴 HIGH | `shared/database.py` | ✅ Separate table creation from migration — `init_db()` returns `True` even if migration fails |
| R5.2 | `process_batch_compute` silently returns empty list when <2 docs extracted | 🟠 MEDIUM | `shared/plagiarism_detector.py` | ✅ Properly fails with error listing which files failed text extraction |
| R5.3 | Add `PYTHONUNBUFFERED=1` to worker environment | 🟢 LOW | `docker-compose.yml` | ✅ Ensures real-time container logs |
| R5.4 | Update status endpoint to include error field | 🟢 LOW | `api-service/main.py` | ✅ Error field propagated in batch status response |
| R5.5 | Frontend nav not auth-aware — shows Login when already logged in | 🟢 LOW | `frontend/src/App.jsx`, `frontend/src/components/RootNav.jsx` | ✅ Login/Sign up hidden when authenticated, nav shows email, AuthPage redirects if logged in |
| R5.6 | Home page hero not auth-aware | 🟢 LOW | `frontend/src/pages/Home.jsx` | ✅ Shows different content based on auth state |
| R5.7 | Update worker tests for new batch compute error flow | 🟢 LOW | `worker-service/tests/test_worker.py` | ✅ Tests verify proper error handling |

### Round 6 — Hybrid Similarity Scorer + Autoscaler Fixes ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R6.1 | Upgrade SBERT model from `all-MiniLM-L6-v2` to `all-MiniLM-L12-v2` | 🟡 MEDIUM | `shared/vectorizer.py` | ✅ 12-layer MiniLM — better semantic quality, ~40MB larger |
| R6.2 | Enable sentence-transformers path in vectorizer | 🟡 MEDIUM | `shared/vectorizer.py` | ✅ `TRY_ST_MODEL` auto-detected; added `sentence-transformers` to deps |
| R6.3 | Create `HybridSimilarityScorer` with configurable alpha blending | 🟡 MEDIUM | `shared/similarity_scorer.py` | ✅ Weighted average of TF-IDF (lexical) + SBERT (semantic) |
| R6.4 | Refactor `TextVectorizer` to expose `_compute_tfidf_matrix()` and `_compute_sbert_matrix()` | 🟢 LOW | `shared/vectorizer.py` | ✅ Split for reuse by hybrid scorer |
| R6.5 | Update worker batch compute to use `HybridSimilarityScorer` | 🟡 MEDIUM | `worker-service/worker.py` | ✅ Alpha=0.5 default — equal weight to lexical + semantic |
| R6.6 | Add `sentence-transformers` to worker requirements | 🟢 LOW | `worker-service/requirements.txt` | ✅ |
| R6.7 | Add 16 tests for `HybridSimilarityScorer` (unit + mocked alpha blending) | 🟢 LOW | `shared/tests/test_similarity_scorer.py` | ✅ Verifies fallback, blending, edge cases |
| R6.8 | Worker Dockerfile: CPU-only PyTorch, pre-download SBERT model at build time | 🟡 MEDIUM | `worker-service/Dockerfile` | ✅ ~569MB unique, 2.33GB disk |
| R6.9 | CI: HuggingFace cache, explicit similarity scorer test job | 🟢 LOW | `.github/workflows/ci.yml` | ✅ |
| R6.10 | Grafana alerting rules (6 rules) | 🟢 LOW | `grafana/provisioning/alerting/rules.yml` | ✅ Queue depth, job failures, worker count, duration, autoscaler activity |
| R6.11 | E2E test for hybrid scorer | 🟢 LOW | `tests/e2e/test_pipeline.py` | ✅ Verifies algorithm label and score range |
| R6.12 | Fix `submit_text` 500 error (`request.text` → `body.text`) | 🔴 HIGH | `api-service/main.py` | ✅ Bug G |
| R6.13 | Fix autoscaler Docker SDK incompatibility (`docker>=7.2.0`) | 🔴 HIGH | `autoscaler/requirements.txt` | ✅ Bug H |
| R6.14 | Fix autoscaler image ref, volume mounts, containers.run() args | 🔴 HIGH | `autoscaler/autoscaler.py` | ✅ Gordon's fixes — verified with stress test (scaled 1→2→3) |
| R6.15 | Fix stress test to use monitoring API instead of broken /status endpoints | 🟠 MEDIUM | `scripts/stress_test.py` | ✅ Bug I |
| R6.16 | Increase API rate limit for stress testing (30→100/min) | 🟢 LOW | `api-service/main.py` | ✅ Bug J |
| R6.17 | Stress test verification: 100 jobs, scaled 1→2→3, 2.09 jobs/sec, 0 failed | 🟡 MEDIUM | — | ✅ Autoscaling confirmed working with Docker SDK 7.2.0 |

---

### Round 7 — AI Content Detection (Phase 1) ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R7.1 | Create `shared/ai_detector.py` with `Hello-SimpleAI/chatgpt-detector-roberta` singleton | 🟡 MEDIUM | `shared/ai_detector.py` | ✅ RoBERTa classifier, returns ai_score [0,1], graceful fallback |
| R7.2 | Pre-download AI detection model in worker Dockerfile | 🟡 MEDIUM | `worker-service/Dockerfile` | ✅ ~500MB, downloaded at build time (36s) |
| R7.3 | Add `update_submission_ai_score()` to database layer | 🟢 LOW | `shared/database.py` | ✅ |
| R7.4 | Integrate AI detection into `process_batch_compute` | 🟡 MEDIUM | `worker-service/worker.py` | ✅ Runs per-submission after text extraction, stores to DB |
| R7.5 | Add AI score badge to frontend submission rows | 🟢 LOW | `frontend/src/pages/Dashboard.jsx`, `frontend/src/styles/portal.css` | ✅ Green/yellow/red based on threshold: 0.3/0.7 |
| R7.6 | Verify end-to-end: upload → compute → ai_score populated in DB + API + CSV | 🟡 MEDIUM | — | ✅ Tested: Alice (human) 0.11, Bob (AI-like) 0.38 |

### Round 8 — Composite Hybrid AI Detector (Phase 2) ✅

| # | Task | Priority | Files | Status |
|---|---|---|---|---|
| R8.1 | Add DistilGPT2 perplexity scoring to `AIContentDetector` | 🟡 MEDIUM | `shared/ai_detector.py` | ✅ Lazy-loaded GPT-2, mean perplexity across sentences |
| R8.2 | Add burstiness score (sentence-level perplexity variance) | 🟡 MEDIUM | `shared/ai_detector.py` | ✅ CoV of per-sentence perplexity |
| R8.3 | Add 5 stylometric features: type-token ratio, sentence-length variance, transition-word frequency, hedge word frequency, passive voice rate | 🟢 LOW | `shared/ai_detector.py` | ✅ Normalized and weighted per heuristic |
| R8.4 | Implement composite weighted blend → final ai_score | 🟡 MEDIUM | `shared/ai_detector.py` | ✅ 50% RoBERTa + 30% PPL/burst + 20% stylo |
| R8.5 | Pre-download DistilGPT2 in worker Dockerfile | 🟡 MEDIUM | `worker-service/Dockerfile` | ✅ ~300MB, downloaded at build time (390s) |
| R8.6 | Rebuild worker container and verify | 🟡 MEDIUM | — | ✅ Tested: Human 0.11, AI academic 0.22, AI formatted 0.38 |

---

## Audit Remediation (from `docs/audit_july2026.md`)

> Comprehensive audit conducted July 18, 2026 — 107 issues found (40 HIGH, 40 MEDIUM, 27 LOW).
> See `docs/audit_july2026.md` for full report with file paths, line numbers, and fix recommendations.

### Round 9 — Tier 1: Critical Fixes ✅

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 9.1 | Raise worker `mem_limit` to 2048m (currently 512m, OOM with ~1.2GB models) | 🔴 CRITICAL | Performance | ✅ |
| 9.2 | Add JWT auth dependency to all portal endpoints (8 endpoints unauthenticated) | 🔴 CRITICAL | Security | ✅ |
| 9.3 | Add DB indexes: `submissions(batch_id)`, `similarity_results(batch_id)`, `submissions(status)`, `jobs(status)` | 🔴 HIGH | Performance | ✅ |
| 9.4 | Remove duplicate nav bars in frontend (main.jsx + per-page both render nav) | 🔴 HIGH | UI/UX | ✅ |
| 9.5 | Replace `alert()` calls in TeacherDashboard with inline `.status-box.error` | 🔴 HIGH | UI/UX | ✅ |
| 9.6 | Add WebSocket reconnection logic (exponential backoff) in `websocket.js` | 🔴 HIGH | UI/UX | ✅ |
| 9.7 | Fix `portal_notify` error leak — replace `detail=str(e)` with generic message | 🔴 HIGH | Resilience | ✅ |
| 9.8 | Fix TOCTOU race on submission — move `previous_submission` check inside `create_submission` transaction | 🔴 HIGH | Resilience | ✅ |
| 9.9 | Add Redis reconnection logic (exponential backoff) in `QueueClient`/`AsyncQueueClient` | 🔴 HIGH | Resilience | ✅ |
| 9.10 | Add zombie job watchdog — detect PROCESSING jobs older than threshold, retry up to 3× then DLQ | 🔴 HIGH | Resilience | ✅ |

### Round 10 — Tier 2: High Priority ✅

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 10.1 | Wrap sync DB calls with `run_in_executor` or migrate to async SQLAlchemy | 🔴 HIGH | Performance | ✅ |
| 10.2 | Move pagination from application-side (load all) to DB-side (SQL LIMIT/OFFSET) | 🟠 MEDIUM | Performance | ✅ |
| 10.3 | Add TTL expiry on Redis job keys (7-day retention) | 🟠 MEDIUM | Performance | ✅ |
| 10.4 | Add `shutil.disk_usage()` check before file writes (return 507 if >95% full) | 🟠 MEDIUM | Resilience | ✅ |
| 10.5 | Add `requirepass` to Redis configuration | 🔴 HIGH | Security | ✅ |
| 10.6 | Replace JWT fallback secret with fail-hard — raise error if `JWT_SECRET` not set | 🔴 HIGH | Security | ✅ |
| 10.7 | Add Docker healthchecks to all 9 services | 🟠 MEDIUM | Resilience | ✅ |
| 10.8 | Fix AI badge contrast ratios — use solid backgrounds instead of `rgba(..., 0.12)` | 🟠 MEDIUM | UI/UX | ✅ |
| 10.9 | Add loading spinners/skeletons instead of plain "Loading..." text | 🟠 MEDIUM | UI/UX | ✅ |
| 10.10 | Add ARIA labels + keyboard navigation (MatrixViewer focus trap, matrix cell keyboard nav) | 🟠 MEDIUM | UI/UX | ✅ |

### Round 11 — Tier 3: Medium Priority ✅

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 11.1 | Add RBAC — `role` column on User, authorization middleware enforcing `owner_user_id` | 🟠 MEDIUM | Security | ✅ |
| 11.2 | Add client-side form validation (email format, password length, empty name check) | 🟠 MEDIUM | UI/UX | ✅ |
| 11.3 | Add toast notification system for success feedback | 🟠 MEDIUM | UI/UX | ✅ |
| 11.4 | Make CollusionGraph responsive (ResizeObserver on parent container) | 🟠 MEDIUM | UI/UX | ✅ |
| 11.5 | Parallelize AI detection in batch compute (ThreadPoolExecutor for model inference) | 🟠 MEDIUM | Performance | ✅ |
| 11.6 | Add magic byte validation for all file extensions (not just PDF/DOCX) | 🟠 MEDIUM | Security | ✅ |
| 11.7 | Add deadline/graceful deadlines to Redis operations and file reads | 🟠 MEDIUM | Resilience | ✅ |
| 11.8 | Close file handles explicitly (PdfReader, Document as context managers) | 🟢 LOW | Resilience | ✅ |
| 11.9 | Pin dependencies to non-vulnerable versions (`requests>=2.32.0`, `redis>=5.1.0`) | 🟢 LOW | Security | ✅ |
| 11.10 | Add `db_ready` periodic retry in case of transient DB unavailability at startup | 🟢 LOW | Resilience | ✅ |

### Round 12 — Tier 4: Future Rounds ✅

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 12.1 | Add external source database lookups (web/academic paper corpus) | 🟠 MEDIUM | Feature | Large | ✅ `shared/external_lookup.py` |
| 12.2 | Add PDF report generation with highlighted similarity passages | 🟠 MEDIUM | Feature | Medium | ✅ `shared/pdf_report.py` + `/portal/report/` endpoint |
| 12.3 | Add per-assignment settings (threshold, due date, file types, anonymous toggle) | 🟢 LOW | Feature | Medium | ✅ Columns + API + migrations |
| 12.4 | Add email notifications (SMTP integration) | 🟢 LOW | Feature | Medium | ✅ `shared/email_notifier.py` + `notifications` DB table |
| 12.5 | Add OCR for scanned documents (image-based PDFs) | 🟢 LOW | Feature | Large | ✅ `shared/ocr_processor.py` (pytesseract + pdf2image) |
| 12.6 | Add Alembic for database migrations (replace raw SQL ALTER TABLE) | 🟢 LOW | Ops | Medium | ✅ `alembic/` configured |
| 12.7 | Add audit logging (access logs, change logs) | 🟢 LOW | Security | Medium | ✅ `shared/audit_log.py` + calls in all key endpoints |
| 12.8 | Add responsive/mobile UI (full mobile breakpoints) | 🟢 LOW | UI/UX | Large | ✅ 768px breakpoint — grids stack, nav collapses |
| 12.9 | Add accessibility features (full a11y pass) | 🟢 LOW | UI/UX | Large | ✅ Skip link, focus-visible, ARIA roles |
| 12.10 | Add cross-batch similarity comparison | 🟢 LOW | Feature | Medium | ✅ `/portal/cross-batch/` + `CrossBatchPage.jsx` |
| 12.11 | Add student-facing comparison details and per-student reports | 🟢 LOW | Feature | Medium | ✅ `/portal/student-comparison/` + `StudentComparison.jsx` |
| 12.12 | Add automated data cleanup / retention policy | 🟢 LOW | Ops | Small | ✅ Hourly task — 30-day deleted cancelled submissions |
| 12.13 | Switch JWT from localStorage to httpOnly cookies | 🟠 MEDIUM | Security | Medium | ✅ httpOnly cookie + localStorage fallback |
| 12.14 | Add CSRF protection | 🟠 MEDIUM | Security | Medium | ✅ `csrf_token` cookie + `X-CSRF-Token` header validation |
| 12.15 | Add admin/super-user panel | 🟢 LOW | Feature | Medium | ✅ `/admin/*` endpoints + `AdminPage.jsx` |

---

### Round 13 — Polish & Future Enhancements (Optional)

| # | Task | Priority | Area | Est. Effort | Notes |
|---|---|---|---|---|---|
| 13.1 | Multi-replica WebSocket scaling (Redis Pub/Sub) | 🟠 MEDIUM | Performance | Medium | Currently single API instance only |
| 13.2 | Run containers as non-root user | 🟠 MEDIUM | Security | Small | Security hardening — added `USER app` in Dockerfiles + `user:` in compose |
| 13.3 | Remove Portainer from docker-compose | 🟢 LOW | Ops | Small | Replaced by monitoring dashboard at :8090 |
| 13.4 | More unit tests (108 total) | 🟢 LOW | Quality | Medium | 108 total (54 new) — all 7 untested shared modules now covered |
| 13.5 | Grafana dashboard for audit events | 🟢 LOW | Monitoring | Small | Done — added `plagioscale-audit` dashboard + audit Prometheus counter |
| 13.6 | `.env.example` cleanup — remove stale secrets | 🟢 LOW | Security | Small | Done — removed host autoscaler, updated secrets |
| 13.7 | Add `docker compose` health status to monitoring dashboard | 🟢 LOW | UI/UX | Small | Done — `/api/health-summary` + health grid in dashboard |
| 13.8 | Rate-limit WebSocket connections per IP | 🟠 MEDIUM | Security | Small | Done — 10 connects/min per IP |
| 13.9 | Add search/filter to admin users table | 🟢 LOW | UI/UX | Small | Done — filter by email, name |
| 13.10 | Pagination on admin users list | 🟢 LOW | UI/UX | Small | Done — 20 per page with nav |
| 13.11 | Dark mode toggle | 🟢 LOW | UI/UX | Medium | Done — CSS variables swap with localStorage persistence |
| 13.12 | Export admin stats as CSV | 🟢 LOW | Feature | Small | Done — `/admin/stats/export` endpoint + button |
| 13.13 | Add service-to-service mTLS | 🟠 MEDIUM | Security | Large | Done — cert generation, volume mounts, HTTPS optional mode |
| 13.14 | Session invalidation on role change | 🟠 MEDIUM | Security | Small | Done — `token_version` column + JWT `ver` claim |
| 13.15 | Live tail of audit log in admin panel | 🟢 LOW | UI/UX | Medium | Done — SSE endpoint `/admin/audit/tail` + Audit tab |
| 13.16 | Multi-replica WebSocket via Redis Pub/Sub | 🟢 LOW | Scaling | Medium | Done — `ws:progress` channel in Redis, listener background task |

---

### Round 14 — CI/CD Pipeline ✅

| # | Task | Priority | Area | Est. Effort | Notes |
|---|---|---|---|---|---|
| 14.1 | Add CD build-and-push job to CI workflow | 🟠 MEDIUM | Ops | Medium | Matrix builds all 5 images, pushes to GHCR on push to `main` |
| 14.2 | Add `image:` alongside `build:` in docker-compose.yml | 🟢 LOW | Ops | Small | Env-var-based image refs (`IMAGE_REPO`, `IMAGE_OWNER`, `IMAGE_TAG`) |
| 14.3 | Create deploy script (`scripts/deploy.sh`) | 🟢 LOW | Ops | Small | One-liner: pull pre-built images + `docker compose up --no-build -d` |
| 14.4 | Create `.dockerignore` + frontend `.dockerignore` | 🟢 LOW | Ops | Small | Speeds up builds by excluding `.git`, `node_modules`, etc. |
| 14.5 | Update AGENTS.md + TODO.md | 🟢 LOW | Docs | Small | Document CI/CD architecture and status |

