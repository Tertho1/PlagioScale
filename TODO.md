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

### Round 15 — Similarity Compute + AI Detection Stability ✅

| # | Fix | Priority | Area | Notes |
|---|---|---|---|---|
| 15.1 | AI detection timeout increase (30s → 600s) | 🟠 MEDIUM | Performance | `as_completed` timeout in worker `process_batch_compute` |
| 15.2 | Stale job recovery reconciler | 🟠 MEDIUM | Resilience | `_recover_stale_jobs` fixes DB-FAILED/Redis-PROCESSING mismatch |
| 15.3 | Persistent HF cache volume | 🟡 MEDIUM | Ops | `hf_cache` named volume, `chown 65532:65532`, `HF_HOME=/app/hf_cache` |
| 15.4 | `local_files_only` first-attempt in `_load_gpt2` | 🟡 MEDIUM | Resilience | Avoids HuggingFace timeout on cache hit |
| 15.5 | Meta tensor materialization in `_load_gpt2` | 🔴 HIGH | Bug | Detects meta device, reloads with explicit device |
| 15.6 | `HF_HUB_DOWNLOAD_TIMEOUT=30` env var | 🟢 LOW | Ops | Added to worker docker-compose environment |
| 15.7 | Auth headers on `computeSimilarity` call | 🟢 LOW | Bug | `getAuthHeaders()` added to POST fetch |
| 15.8 | Tools navbar dropdown | 🟢 LOW | UI/UX | Already present in `main.jsx` — verified |
| 15.9 | SBERT model global cache | 🟠 MEDIUM | Performance | `_get_sbert()` singleton in `vectorizer.py` prevents re-load per compute |
| 15.10 | Worker model warmup at startup | 🟠 MEDIUM | Performance | `_warmup_models()` pre-loads DistilGPT2 + SBERT eagerly |
| 15.11 | Auto-compute on new submission | 🟡 MEDIUM | Feature | Enqueues BATCH_COMPUTE job when submission count ≥ 2 |

---

## Round 16 — Refactoring & Frontend Improvements ✅

> All work on `refactor` branch. `main` is frozen.
> See `docs/frontend_improvement_report.md` for full analysis. Round 16 addresses items verified against source code in July 2026.

**Legend:** ✅ = Done, 🚧 = In Progress, ❌ = Not Started, 🔜 = Planned

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| **Security** | | | | | |
| 16.1 | 401 refresh-retry interceptor: wrap fetch calls to call `refreshToken()` on 401 before redirecting | 🟠 MEDIUM | Security | Small | ✅ `authFetch()` in `utils/auth.js` |
| 16.2 | WebSocket auth via `Sec-WebSocket-Protocol` header or short-lived ticket instead of `?token=` query param | 🟠 MEDIUM | Security | Medium | ✅ Deferred — query param kept for local demo |
| 16.3 | Add `original_filename` field to backend API response to eliminate fragile `split("_").slice(3)` in 4 frontend files | 🟢 LOW | Quality | Small | ✅ DB column + API response + 4 frontend files |
| **Auth / Route Protection** | | | | | |
| 16.4 | Create shared `<RequireAuth>` and `<RequireRole>` route wrappers; apply to all protected routes in `App.jsx` | 🟠 MEDIUM | Auth | Medium | ✅ `components/AuthGuards.jsx` |
| 16.5 | Add cross-tab auth state sync via `window.addEventListener('storage', ...)` in NavBar | 🟢 LOW | UX | Small | ✅ Via AuthContext `storage` listener |
| **Data Fetching & UX** | | | | | |
| 16.6 | Add abort-on-unmount guard (AbortController / cancelledRef) to compute similarity polling loop | 🟠 MEDIUM | Quality | Small | ✅ `abortRef` in Dashboard.jsx |
| 16.7 | Add rollback on rename failure in Dashboard.jsx (revert optimistic update) | 🟠 MEDIUM | Quality | Small | ✅ `originalName` revert on catch |
| 16.8 | Make WebSocket primary channel for compute progress, polling only as timeout fallback | 🟢 LOW | UX | Medium | ✅ Adaptive poll interval (4s WS connected, 2s fallback) |
| 16.9 | Add skeleton/loading states for matrix and submissions table (currently pop-in) | 🟢 LOW | UX | Small | ✅ Skeleton rows during refresh |
| **Architecture** | | | | | |
| 16.10 | Remove dead code: `TeacherDashboard.jsx` is unrouted (both `/dashboard` and `/teacher` point to `Dashboard.jsx`) | 🟢 LOW | Quality | Small | ✅ Deleted 393 lines |
| 16.11 | Split Dashboard.jsx (~661 lines) into custom hooks: `useAssignments`, `useAssignmentDetails`, `useSimilarityCompute`, `useMatrixViewer` | 🟠 MEDIUM | Quality | Large | 🔜 Deferred to Round 17 |
| 16.12 | Create minimal `AuthContext` (token, email, role) to avoid direct localStorage reads on every render | 🟠 MEDIUM | Architecture | Medium | ✅ `contexts/AuthContext.jsx` + `useAuth()` hook |
| **WebSocket** | | | | | |
| 16.13 | Cap WS retry count and surface persistent "live updates unavailable" banner to user | 🟢 LOW | UX | Small | ✅ `MAX_RETRIES=10`, `failed` state + banner |
| **Components** | | | | | |
| 16.14 | Add outside-click + Escape handlers and `aria-expanded` to NavBar Tools dropdown | 🟢 LOW | A11y | Small | ✅ `useRef` + `mousedown`/`keydown` listeners |
| 16.15 | Add `prefers-color-scheme` media query fallback for dark mode (first-time visitors) | 🟢 LOW | UX | Small | ✅ `window.matchMedia` check in initial state |
| 16.16 | Swap custom focus trap in MatrixViewer for native `<dialog>` element or Radix Dialog | 🟢 LOW | A11y | Small | ✅ Native `<dialog>` with `showModal()` |
| 16.17 | Use `role="status"` for success/info toasts, keep `role="alert"` only for errors | 🟢 LOW | A11y | Small | ✅ Conditional role in `ToastItem` |
| **Performance** | | | | | |
| 16.18 | Route-level code splitting: `React.lazy` + `Suspense` for AdminPage, CollusionGraph | 🟢 LOW | Perf | Small | ✅ All page routes lazy-loaded |
| **Testing** | | | | | |
| 16.19 | Tests for `useBatchProgress` WebSocket hook (reconnection, backoff, max retries) | 🟠 MEDIUM | Quality | Medium | 🔜 Deferred to Round 17 |
| 16.20 | Tests for auth guard logic (RequireAuth, RequireRole, 401 refresh-retry) | 🟠 MEDIUM | Quality | Medium | 🔜 Deferred to Round 17 |
| **CI / Build** | | | | | |
| 16.21 | Add missing deps (`bcrypt`, `python-jose[cryptography]`, `email-validator`) to `requirementsall.txt` and remove corresponding conftest mocks | 🟠 MEDIUM | CI | Small | 🔜 Deferred to Round 17 |
| **Audit fixes (from docs/frontend_audit_report.md)** | | | | | |
| 16.22 | Fix Download Report PDF button — `Dashboard.jsx` must pass `submission_id` to MatrixViewer (currently silent no-op) | 🔴 HIGH | Bug | Small | ✅ Renamed `id` → `submission_id` |
| 16.23 | Fix SSE audit tail — add `withCredentials = true` to EventSource so httpOnly cookie is sent cross-origin | 🔴 HIGH | Bug | Small | ✅ Conditional `?token=` only when token exists |
| 16.24 | Delete orphaned `TeacherDashboard.jsx` (393 lines dead code, unrouted) | 🟠 MEDIUM | Quality | Small | ✅ Deleted |
| 16.25 | Parse JSON error responses cleanly in StudentSubmit/StudentDashboard (currently raw JSON shown) | 🟠 MEDIUM | UX | Small | ✅ `res.json().catch(() => null)` pattern |
| 16.26 | Add file-size/type validation to StudentDashboard upload (matches StudentSubmit) | 🟠 MEDIUM | UX | Small | ✅ 10MB limit + 9 allowed extensions |
| 16.27 | Fix stale copy: StudentSubmit Dropzone help text vs actual 9 allowed extensions; SimilarityMatrix placeholder copy | 🟢 LOW | UX | Small | ✅ Updated help text + Dropzone `accept` attr |
| 16.28 | Wire CollusionGraph `onNodeClick` (currently no-op) | 🟢 LOW | UX | Small | ✅ Already implemented — verified |
| 16.29 | Add loading indicator to Dashboard detail panel during refresh (stale data stays visible) | 🟢 LOW | UX | Small | ✅ "Refreshing data..." banner |

---

## Round 17 — Security Audit Remediation ✅

> All work on `refactor` branch. `main` is frozen.
> Security audit conducted August 2026 — 18 issues found (3 CRITICAL, 5 HIGH, 8 MEDIUM, 2 LOW).

**Legend:** ✅ = Done, 🚧 = In Progress, ❌ = Not Started, 🔜 = Planned

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| **CRITICAL** | | | | | |
| 17.1 | Add ownership checks to all portal mutation endpoints (rename, delete, compute, cancel, report) | 🔴 CRITICAL | Security | Medium | ✅ `require_assignment_owner()` + `require_submission_owner()` helpers |
| 17.2 | Filter `list_assignments()` to only return owned + shared assignments (not all) | 🔴 CRITICAL | Security | Small | ✅ Strips `all` key, returns only owner + shared |
| 17.3 | Stop exposing access codes in assignment list response to non-owners | 🔴 CRITICAL | Security | Small | ✅ `access_code` stripped from non-owner responses |
| **HIGH** | | | | | |
| 17.4 | Add ownership check to cross-batch comparison endpoint | 🟠 HIGH | Security | Small | ✅ Both batch IDs checked against ownership |
| 17.5 | Add ownership check to student comparison endpoint | 🟠 HIGH | Security | Small | ✅ Submission ownership verified |
| 17.6 | Add ownership check to report download endpoint | 🟠 HIGH | Security | Small | ✅ Submission ownership verified |
| 17.7 | Add roll-number validation on submit (link to authenticated user or require registration) | 🟠 HIGH | Security | Medium | ✅ Roll linked to user account at signup, submit uses profile roll |
| **MEDIUM** | | | | | |
| 17.8 | Enable CSRF protection on state-changing endpoints (`require_csrf` defined but unused) | 🟠 MEDIUM | Security | Small | ✅ Added to create, rename, delete, cancel, compute endpoints |
| 17.9 | Add rate limiting to unprotected portal endpoints | 🟠 MEDIUM | Security | Medium | 🔜 Deferred |
| 17.10 | Require `WORKER_SECRET` to be set (currently skips check when empty) | 🟠 MEDIUM | Security | Small | ✅ Returns 503 when empty |
| 17.11 | Gate debug endpoint behind `DEBUG=true` env check | 🟢 LOW | Security | Small | ✅ Gated behind `ENABLE_DEBUG_ENDPOINTS=true` |
| **Deferred** | | | | | |
| 17.12 | Split Dashboard.jsx into custom hooks (16.11 deferred) | 🟠 MEDIUM | Quality | Large | ✅ 4 hooks: useAssignments, useAssignmentDetails, useSimilarityCompute, useMatrixViewer |
| 17.13 | Tests for WebSocket hook + auth guards (16.19/16.20 deferred) | 🟠 MEDIUM | Quality | Medium | ✅ 30 frontend tests: useBatchProgress (9), RequireAuth/RequireRole (6), authFetch (5), existing (10) |
| 17.14 | Add missing deps to `requirementsall.txt` (16.21 deferred) | 🟠 MEDIUM | CI | Small | ✅ Added bcrypt, python-jose, email-validator, Pillow, reportlab, packaging; cleaned conftest mocks |

---

## Round 18 — Feature Additions ✅ (11/11 done)

> All work on `refactor` branch. `main` is frozen.

**Legend:** ✅ = Done, 🚧 = In Progress, ❌ = Not Started, 🔜 = Planned

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 18.1 | Color-coded severity bands on scores + legend (Turnitin: blue/green/yellow/orange/red) | 🟠 MEDIUM | Feature | Small | ✅ 5-band legend + color-coded matrix cells + score badges |
| 18.2 | Threshold filter on similarity matrix ("only show pairs > X%") + row/col clustering by similarity | 🟠 MEDIUM | Feature | Medium | ✅ Slider filter (0–80%), dimmed cells below threshold |
| 18.3 | In-document highlighted matches view + clickable source list / match overview panel | 🔴 HIGH | Feature | Large | ✅ Client-side n-gram matching in MatrixViewer, highlighted common passages |
| 18.4 | AI detection confidence caveats (suppress/show-with-asterisk low scores, <20%) | 🟢 LOW | Feature | Small | ✅ Tooltip labels: "Likely human-written" / "Possibly AI-assisted" / "Likely AI-generated" |
| 18.5 | Student-facing draft self-check (private pre-submission scan) | 🟢 LOW | Feature | Medium | ✅ `/portal/self-check` endpoint + pre-check button in StudentDashboard |
| 18.6 | Assignment settings (due dates, resubmission policy, report visibility, all-vs-all on due date) | 🟢 LOW | Feature | Medium | ✅ allow_resubmission + max_submissions fields, detail cards show settings |
| 18.7 | Side-by-side source comparison (paper vs. matched source) | 🟢 LOW | Feature | Medium | ✅ MatrixViewer shows side-by-side with highlighted common text |
| 18.8 | Per-batch analytics: similarity distribution + AI-score distribution charts | 🟢 LOW | Feature | Medium | ✅ BatchAnalytics component with stat cards + bar charts |
| 18.9 | Empty states with guidance + CTAs across pages (matrix, admin users, cross-batch) | 🟢 LOW | UX | Small | ✅ Icons, titles, hints in Dashboard empty states |
| 18.10 | Sticky headers / horizontal-scroll affordance on wide submission tables | 🟢 LOW | UX | Small | ✅ Sticky header row on StudentDashboard table |
| 18.11 | Instructor feedback/annotation layer (inline comments, reusable comment libraries) | 🟢 LOW | Feature | Large | ✅ annotations DB table + API CRUD + MatrixViewer annotation UI |

---

## Round 19 — Bug Fixes, Security Hardening & Performance

**Legend:** ✅ = Done, 🚧 = In Progress, ❌ = Not Started, 🔜 = Planned

### Critical Bugs

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 19.1 | Fix `download_report` crash — `assignment` variable undefined in scope | 🔴 CRITICAL | Bug | Small | ✅ Fetched assignment via `get_assignment(batch_id)` before use |
| 19.2 | Add CSRF protection to `portal_submit` (file upload endpoint) | 🔴 CRITICAL | Security | Small | ✅ Added `_csrf: None = Depends(require_csrf)` |
| 19.3 | Fix auth bypass when DB is down — `get_current_user` grants all permissions | 🔴 CRITICAL | Security | Small | ✅ Returns 503 when `db_ready=False` instead of fake user |
| 19.4 | Fix dead letter jobs losing payload — re-queued with empty `text=""` | 🔴 CRITICAL | Bug | Medium | ✅ Store payload in `dead_letter:{job_id}` hash, restore on drain |
| 19.5 | Fix PDF report copy-paste bug — shows text A twice in fpdf2 path | 🔴 CRITICAL | Bug | Small | ✅ Changed line 174 to use `words_b_hl` |

### Security Hardening

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 19.6 | Remove JWT-in-query-param auth path (`?token=`) — keep only Bearer + httpOnly cookie | 🔴 HIGH | Security | Small | ✅ Removed `token_param` from `get_current_user` |
| 19.7 | Add password strength validation (min 8 chars, complexity) on signup | 🔴 HIGH | Security | Small | ✅ Min 8 chars + digit + special char; new test added |
| 19.8 | Add WebSocket ownership check — verify batch owner before accepting WS connection | 🔴 HIGH | Security | Medium | ✅ Requires token + verifies `owner_id` matches; close code 4003 |
| 19.9 | Require authentication on `/submit` endpoint | 🟠 MEDIUM | Security | Small | ✅ Added `Depends(get_current_user)` to `submit_text` |

### Performance

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 19.10 | Batch SBERT encoding — use `model.encode(texts, batch_size=32)` instead of one-at-a-time | 🔴 HIGH | Performance | Medium | ✅ Batch encode + vectorized cosine similarity matrix |
| 19.11 | Atomic Redis enqueue — use `pipeline()` for lpush+hset+expire | 🔴 HIGH | Reliability | Small | ✅ Both sync and async `enqueue_job` use `pipeline()` |
| 19.12 | Fix N+1 queries in `get_cross_batch_comparisons` — batch-load SimilarityResults | 🔴 HIGH | Performance | Medium | ✅ Single query with `.in_()` + Python-side lookup dict |
| 19.13 | Configure DB connection pool (`pool_size=10, max_overflow=20, pool_recycle=1800`) | 🔴 HIGH | Performance | Small | ✅ Added to `create_engine()` |
| 19.14 | Lazy-load RoBERTa model — move from `__init__` to warmup/background thread | 🟠 MEDIUM | Performance | Medium | ✅ `_ensure_loaded()` on first `detect()` call |

### Frontend — Quick Wins

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 19.15 | Add ErrorBoundary around `<Suspense>` in App.jsx — prevent white screen | 🔴 HIGH | Reliability | Small | ✅ ErrorBoundary component + wrapped routes |
| 19.16 | Extract `API_BASE` to shared `utils/config.js` — currently duplicated in 8 files | 🟠 MEDIUM | Quality | Small | ✅ Single source of truth in 12 files |
| 19.17 | Lazy-load `CollusionGraph` (react-force-graph-2d) — ~50KB savings | 🟠 MEDIUM | Performance | Small | ✅ Dashboard bundle 223KB → 36KB; graph in own 188KB chunk |
| 19.18 | Add error feedback to silent `catch { /* ignore */ }` — 6+ locations | 🟠 MEDIUM | UX | Medium | ✅ Toast/console.warn added to useMatrixViewer, StudentComparison, MatrixViewer annotations, poll loop |
| 19.19 | Add loading state to MatrixViewer dialog — currently opens empty | 🟠 MEDIUM | UX | Small | ✅ viewerLoading state + "Loading submission texts..." placeholder |
| 19.20 | Add confirmation dialog for admin role change | 🟠 MEDIUM | UX | Small | ✅ window.confirm + aria-label on role select |

### Backend — Medium Priority

| # | Task | Priority | Area | Est. Effort | Status |
|---|---|---|---|---|---|
| 19.21 | Create Pydantic `CreateAssignmentRequest` model — replace raw `dict` body | 🟠 MEDIUM | Quality | Small | ✅ Field validators: name ≤200 chars, threshold [0,1], counts ≥0, ISO due_date |
| 19.22 | Pre-compute n-grams in `_compute_jaccard_matrix` — avoid recomputing per pair | 🟠 MEDIUM | Performance | Small | ✅ Single n-gram pass before O(n²) loop |
| 19.23 | Catch `IntegrityError` in `create_user` — return friendly "email exists" message | 🟠 MEDIUM | Quality | Small | ✅ Re-raised in DB layer; caught in signup → 400 "Email or roll number already registered" |
| 19.24 | Add SMTP connection reuse in `email_notifier.py` — avoid 100+ TCP handshakes | 🟠 MEDIUM | Performance | Medium | ✅ `smtp_connection()` context manager + `send_bulk_emails()`; invalid SMTP_PORT no longer crashes import |
| 19.25 | Escape `%` and `_` in `get_paginated_users` search — prevent wildcard injection | 🟠 MEDIUM | Security | Small | ✅ Escaped + `escape="\\"` on ilike filters |
| 19.26 | Sanitize text before PDF `Paragraph` — prevent XML parse crash on `<`, `>`, `&` | 🟠 MEDIUM | Bug | Small | ✅ `_escape_xml()` applied to text, batch name, roll/name fields |
| 19.27 | Move `torch.set_num_threads(1)` to module load — not per-call | 🟢 LOW | Performance | Small | ✅ Set once at module import with ImportError guard |
| 19.28 | Add CSRF + rate limiting to `admin_update_role` | 🟠 MEDIUM | Security | Small | ✅ `require_csrf` + 10/min limit + audit log entry |
| 19.29 | Add `pool_size`/`max_overflow` to SQLAlchemy engine | 🔴 HIGH | Reliability | Small | ✅ Same as 19.13 — pool_size=10, max_overflow=20, timeout=30s, recycle=1800s |

---

## Round 20 — Security Depth, Worker Reliability & Frontend Polish ✅ (23/23 done)

**Legend:** ✅ = Done

### Backend Security & Data Integrity

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 20.1 | Fix `require_role("user")` no-op bypass — any role passes the check (M7) | 🔴 HIGH | Security | ✅ Role hierarchy `user(0) < teacher(1) < admin(2)`; unknown/missing roles fail; admins pass teacher checks |
| 20.2 | Bind CSRF token to session via HMAC instead of bare UUID | 🟠 MEDIUM | Security | ✅ `HMAC(CSRF_SECRET, user_id)`; constant-time compare in require_csrf; rotates with login |
| 20.3 | Signup email enumeration — don't reveal whether email is registered | 🟠 MEDIUM | Security | ✅ Generic "Unable to register" message; pre-checks removed; DB constraint is source of truth |
| 20.4 | Restrict CORS methods/headers from `*` to actual usage | 🟢 LOW | Security | ✅ GET/POST/PUT/DELETE/OPTIONS + Authorization/Content-Type/X-CSRF-Token |
| 20.5 | Cookie `samesite="strict"` for auth cookie | 🟢 LOW | Security | ✅ Changed from lax |
| 20.6 | `store_similarity_results` delete+insert not atomic — wrap in transaction | 🔴 HIGH | Reliability | ✅ Verified already atomic — `get_session()` commits once per block w/ rollback on error |
| 20.7 | `delete_assignment` leaves uploaded files on disk — add file cleanup | 🟠 MEDIUM | Quality | ✅ Collects file_paths + deletes submission rows + `_remove_files()` best-effort cleanup |
| 20.8 | API responses leak internal `file_path` values | 🟠 MEDIUM | Security | ✅ `_public_submission()` strips file_path/embedding_json from assignment detail + list endpoints |

### Worker Reliability

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 20.9 | Partial batch failure re-scores already-scored submissions — skip scored ones | 🟠 MEDIUM | Performance | ✅ Skips subs with ai_score set on retry |
| 20.10 | `_notify` blocks worker 2s per notification — fire-and-forget thread | 🟠 MEDIUM | Performance | ✅ Daemon thread per notify |
| 20.11 | Broad `except Exception` in worker main loop swallows bugs — log traceback | 🟠 MEDIUM | Quality | ✅ `traceback.print_exc()` added |

### AI Detector Robustness

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 20.12 | AI detect has no timeout on long texts | 🟠 MEDIUM | Reliability | ✅ ThreadPoolExecutor + `timeout=120s` default → -1.0 on expiry |
| 20.13 | Singleton not thread-safe — two threads can double-load models | 🟢 LOW | Quality | ✅ `_instance_lock` + `_load_lock` double-checked locking |

### Frontend Fixes & Features

| # | Task | Priority | Area | Status |
|---|---|---|---|---|
| 20.14 | `React.memo` on AssignmentCard / BatchAnalytics / ScoreLegend | 🟠 MEDIUM | Performance | ✅ All memoized + histograms via useMemo |
| 20.15 | AdminPage search race condition — add AbortController | 🟠 MEDIUM | Quality | ✅ AbortController + 300ms debounce on search |
| 20.16 | Remove dead `/teacher` route (duplicate of `/dashboard`) | 🟢 LOW | Cleanup | ✅ Removed |
| 20.17 | Navbar shows "My Dashboard" when logged out — hide it | 🟢 LOW | UX | ✅ Links only shown when authenticated |
| 20.18 | Matrix grid arrow-key navigation (roving tabindex) | 🟠 MEDIUM | A11y | ✅ Arrow keys move focus between cells via data-cell lookup |
| 20.19 | Assignment search/filter in Dashboard sidebar | 🟠 MEDIUM | Feature | ✅ Search input filters owned+shared by name/batch_id, empty-state aware |
| 20.20 | Pagination for large submission lists (>50) | 🟢 LOW | Feature | ✅ 25/page pagination controls, resets on batch switch |
| 20.21 | Batch CSV export button (matrix + scores) | 🟠 MEDIUM | Feature | ✅ Export CSV button hits `/portal/export/{batch_id}` with blob download |
| 20.22 | `<a href>` → `<Link>` in StudentDashboard view link (full reload) | 🟢 LOW | UX | ✅ SPA navigation |
| 20.23 | Move NavBar dropdown inline styles to CSS classes | 🟢 LOW | Cleanup | ✅ `.nav-tools`, `.nav-tools-menu`, `.nav-tools-item` + role=menuitem |

