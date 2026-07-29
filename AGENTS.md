# PlagioScale — Agent Context

## Project Overview

PlagioScale is a cloud-native, microservices-based plagiarism detection platform that runs entirely locally via Docker Compose. No cloud services, no paid APIs.

## Stack

- **Backend:** Python FastAPI (4 services: api, worker, autoscaler, monitoring)
- **Frontend:** React + Vite (served via Nginx)
- **Database:** PostgreSQL 16 (Docker)
- **Queue:** Redis 7 (Docker)
- **Monitoring:** Prometheus + Grafana
- **Auth:** JWT (bcrypt passwords)

## Branch Strategy

| Branch | Purpose | State |
|---|---|---|
| `main` | Stable, working, demo-ready product. All tests pass. CI/CD runs. | 🔒 **Frozen** — no direct pushes or PRs |
| `refactor` | All planned improvements, refactoring, and new work. | 🚧 **Active** — push here after work is done |

**Rule:** `main` is always green. Work only on `refactor`. Merge to `main` only when explicitly discussed and confirmed.

## Commit & Push Rules

- **Never push to GitHub without explicit confirmation from the user.**
- Before any push, the AI must ask: *"Ready to push to `refactor`?"* and wait for a yes.
- After push confirmation, push to `refactor` only (never `main`).

## Key Architecture Decisions

| Decision | Choice |
|---|---|
| Async Redis in API | Implemented — `AsyncQueueClient` in `shared/queue_client.py` (Phase 2) |
| Autoscaler | In-container (Docker SDK) — host variant deleted (Round 2) |
| JWT storage | httpOnly cookies + CSRF (primary). localStorage fallback for JS access. XSS-vulnerable localStorage path kept for local demo convenience. httpOnly cookie path provides real CSRF/XSS protection. (Round 12) |
| WebSocket scaling | Single API instance only — no Redis Pub/Sub for multi-replica yet |
| Resource limits | Set on all services in docker-compose.yml (Phase 0) |
| Similarity engine | Hybrid `HybridSimilarityScorer` — TF-IDF (lexical) + SBERT `all-MiniLM-L12-v2` (semantic), blended via configurable alpha (default 0.5) |
| AI detection (Phase 1) | `AIContentDetector` in `shared/ai_detector.py` — `Hello-SimpleAI/chatgpt-detector-roberta` RoBERTa classifier, singleton, returns ai_score [0,1] |
| AI detection (Phase 2) | Composite hybrid: RoBERTa classifier (primary, 50%) + DistilGPT2 perplexity/burstiness (secondary, 30%) + 5 stylometric features (tertiary, 20%), weighted blend → final ai_score |
| Email notifications | `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` env vars; `shared/email_notifier.py` with `send_email()`/`notify_completion()`; pending queue in `notifications` DB table |
| PDF reports | `shared/pdf_report.py` via reportlab (preferred) or fpdf2 fallback; generated on-demand at `/portal/report/{batch_id}/{sub_id_1}/{sub_id_2}` |
| External lookup | `shared/external_lookup.py` — phrase extraction + simulated web/academic search with in-memory cache |
| OCR | `shared/ocr_processor.py` — pytesseract + pdf2image for scanned PDFs and images |
| Admin panel | `/admin/stats`, `/admin/users`, `/admin/users/{id}/role`, `/admin/notifications/send` — all protected by `require_role("admin")` |
| Cross-batch | `/portal/cross-batch/{batch_id_1}/{batch_id_2}` — compares active submissions across two batches |
| Student comparison | `/portal/student-comparison/{submission_id}` — returns all pairwise scores for a student's submission |
| DB migrations | Alembic configured in `alembic/` directory (`alembic.ini`, `env.py`, `script.py.mako`) |
| Audit logging | `shared/audit_log.py` writes structured JSON to `/app/logs/audit.log` |
| Session invalidation | `token_version` column on User — JWT `ver` claim checked on every request; incremented on role change → forces re-login (Round 13) |
| Non-root containers | api-service, worker-service run as UID 1000 (`app` user). Frontend nginx runs as root (required for port 80). Autoscaler/monitoring-service stay root (need Docker socket). (Round 13) |
| WS rate limiting | 10 WebSocket connections per IP per 60s window (`_check_ws_rate`) (Round 13) |
| Admin users pagination | `/admin/users?search=&page=&per_page=` with search by email/name, 20 per page (Round 13) |
| Admin stats CSV | `/admin/stats/export` — downloads system statistics as CSV (Round 13) |
| Live audit log | SSE endpoint at `/admin/audit/tail` + Audit tab in admin panel (Round 13) |
| WebSocket scaling | Redis Pub/Sub `ws:progress` channel — all replicas receive progress events (Round 13) |
| Compose health | `/api/health-summary` endpoint + health grid in monitoring dashboard (Round 13) |
| mTLS | Optional `USE_MTLS=true` — auto-generated certs in `certs/`, uvicorn SSL, worker client certs (Round 13) |
| Dark mode | CSS variables swap with `[data-theme]` + localStorage persistence — toggle in navbar (Round 13) |
| More unit tests | 108 tests total (+54) covering all 7 previously-untested shared modules (Round 13) |
| Periodic DB reconnection | `_monitor_db()` background task retries `init_db()` every 30s when `db_ready` is False (Self-Healing) |
| Dependency-aware /health | `/health` pings Redis + DB and returns `degraded` status if either is down (Self-Healing) |
| Periodic stale-job recovery | `_recover_stale_jobs()` runs every 60s in worker main loop (Self-Healing) |
| Failed job retry | Jobs re-enqueued up to `MAX_RETRIES` (3) with backoff via `STALE_RETRY_KEY` before dead letter (Self-Healing) |
| Dead-letter consumer | `_drain_dead_letter()` runs every 60s — re-queues jobs under max retries, logs exhausted ones (Self-Healing) |
| Alertmanager webhook | `prometheus/alertmanager.yml` + `prometheus/alerts.yml` + `/api/webhooks/alertmanager` endpoint with auto-remediation counters (Self-Healing) |
| CI/CD | Build-and-push to GHCR on push to `main` — 5 images built via matrix (api, worker, autoscaler, monitoring, frontend), tagged with commit SHA + `latest`, pushed to `ghcr.io/{owner}/plagioscale-{service}`. Deploy via `IMAGE_OWNER=x IMAGE_TAG=latest bash scripts/deploy.sh`. `docker-compose.yml` has `image:` alongside `build:` — set env vars to pull pre-built images. (Round 14) |

## Known Bugs (audit July 2026) — All Fixed ✅

| ID | Bug | Severity | Round | Status |
|---|---|---|---|---|
| A | `get_user_by_email` missing `password_hash` — login broken for all users | 🔴 HIGH | Round 1 | ✅ Fixed |
| B | `create_assignment` returns success on silent DB write failure | 🟠 MEDIUM | Round 1 | ✅ Fixed |
| C | `StudentDashboard.jsx` upload missing required `roll` field → 422 | 🟠 MEDIUM | Round 1 | ✅ Fixed |
| D | `init_db()` returns `False` on migration failure → worker never queries DB | 🔴 HIGH | Round 5 | ✅ Fixed |
| E | `process_batch_compute` silently returns empty list on <2 docs extracted | 🟠 MEDIUM | Round 5 | ✅ Fixed |
| F | Frontend nav not auth-aware (shows Login when logged in, lacks user context) | 🟢 LOW | Round 5 | ✅ Fixed |
| G | `submit_text` uses `request.text` instead of `body.text` → 500 on submit | 🔴 HIGH | Round 6 | ✅ Fixed |
| H | Autoscaler `docker==7.0.0` incompatible with `urllib3==2.7.0` (http+docker scheme) | 🔴 HIGH | Round 6 | ✅ Fixed |
| I | Stress test references nonexistent `/status` endpoints (autoscaler uses Prometheus, worker port not exposed) | 🟠 MEDIUM | Round 6 | ✅ Fixed |
| J | API rate limit 30/min too low for stress testing | 🟢 LOW | Round 6 | ✅ Fixed |

## Work Rules

- **Branch:** All work goes to `refactor` branch. `main` is frozen.
- **No push without confirmation.** Always ask: *"Ready to push?"* before any `git push`.
- **Never push to GitHub unless explicitly asked.** All work is local unless the user says otherwise.
- **Keep `main` green.** The `main` branch must always pass all tests and be demo-ready.

See `TODO.md` for full round-by-round fix plan and planned improvements.
See `docs/audit_july2026.md` for comprehensive audit report.
See `docs/setup_guide.md` for full setup and demo instructions.
See `docs/frontend-architecture.md` for frontend architecture documentation.

## Folder Structure

```
api-service/         # FastAPI REST API (port 8000)
worker-service/      # Background job processor (port 8001)
autoscaler/          # In-container autoscaler (port 8002)
monitoring-service/  # Live monitoring dashboard (port 8090)
shared/              # Python modules shared across all services
frontend/            # React + Vite + Nginx (port 3050)
scripts/             # Utility scripts (stress test, seed data, pg_backup, deploy)
docs/                # Planning docs + archived reports
prometheus/          # Prometheus scrape config + alerts + alertmanager config
grafana/             # Pre-provisioned dashboards
.github/workflows/   # GitHub Actions CI + CD
```

## Status

**`main` branch — stable, demo-ready.**
All 107 audit issues ✅ — All 15 Round 12 features ✅ — All 15 Round 13 features ✅ — Round 14 CI/CD ✅ — 171 tests ✅ — 6 Self-Healing mechanisms — E2E verified — Stress test: 28ms avg latency — CI + CD ready

**No active work on `refactor` yet.** See TODO.md → Round 16 for planned improvements.

## Round 15 — Similarity Compute + AI Detection Stability ✅

| # | Fix | Status | Notes |
|---|---|---|---|
| 15.1 | AI detection timeout increase (30s → 600s) | ✅ | `as_completed` timeout in `process_batch_compute` |
| 15.2 | Stale job recovery reconciler | ✅ | `_recover_stale_jobs` fixes DB-FAILED/Redis-PROCESSING mismatch |
| 15.3 | Persistent HF cache volume | ✅ | `hf_cache` named volume, `chown 65532:65532`, `HF_HOME=/app/hf_cache` |
| 15.4 | `local_files_only` first-attempt in `_load_gpt2` | ✅ | Avoids HuggingFace timeout on cache hit |
| 15.5 | Meta tensor materialization in `_load_gpt2` | ✅ | Detects meta device, reloads with explicit device |
| 15.6 | `HF_HUB_DOWNLOAD_TIMEOUT=30` env var | ✅ | Added to worker docker-compose environment |
| 15.7 | Auth headers on `computeSimilarity` call | ✅ | `getAuthHeaders()` added to POST fetch |
| 15.8 | Tools navbar dropdown | ✅ | Already present in `main.jsx` — verified |
