# PlagioScale — Comprehensive Audit Report

**Date:** July 18, 2026
**Scope:** Full codebase — security, performance, resilience, UI/UX, feature gaps

---

## 1. SECURITY — 23 issues (11 HIGH, 9 MEDIUM, 3 LOW)

### 1.1 Critical: Unauthenticated Portal Endpoints 🔴

**7 portal endpoints + 1 debug endpoint have no authentication.** Anyone on the network who knows a batch_id (UUID) can read all submissions, similarity matrices, and export CSVs.

| Endpoint | File:Line |
|---|---|
| `POST /portal/compute-similarity/{batch_id}` | `api-service/main.py:699` |
| `GET /portal/similarity-matrix/{batch_id}` | `api-service/main.py:734` |
| `GET /portal/submissions/{batch_id}` | `api-service/main.py:744` |
| `GET /portal/export/{batch_id}` | `api-service/main.py:758` |
| `GET /portal/submissions/{batch_id}/{submission_id}/text` | `api-service/main.py:836` |
| `POST /portal/notify` | `api-service/main.py:466` |
| `WS /portal/ws/{batch_id}` | `api-service/main.py:678` |
| `GET /debug/test-extraction/{batch_id}` | `api-service/main.py:850` |

**Fix:** Add JWT auth dependency to all portal endpoints. Use `get_current_user` dependency.

### 1.2 Critical: No Secrets Management 🔴

| Issue | Detail | File:Line |
|---|---|---|
| JWT fallback secret | `"please-change-this-secret"` — guessable | `api-service/main.py:166` |
| DB password hardcoded | `plagio_pass` in 3 places + Python fallback | `docker-compose.yml:8,55,93`, `shared/database.py:27` |
| Redis has no password | Anyone on network can read/write queue | `docker-compose.yml:24-40` |
| Grafana default creds | `admin/admin` — no `GF_SECURITY_ADMIN_PASSWORD` set | `docker-compose.yml:182` |
| Docker socket in 3 containers | Container escape risk | `docker-compose.yml:127,152,205` |

**Fix:** Generate random secrets at deploy time via `.env` file. Add `requirepass` to Redis. Set Grafana admin password. Audit Docker socket mounts.

### 1.3 Critical: No Role-Based Access Control 🔴

The `User` model has no `role` field. Any authenticated user can create/read/modify ANY assignment. `owner_user_id` is stored but **never enforced**.

**Fix:** Add `role` column to `User` model. Add authorization middleware checking `owner_user_id` on assignment endpoints.

### 1.4 Medium: File Upload Gaps 🟠

- Code file extensions (`.py`, `.js`, `.ts`, `.java`, `.csv`) allowed with **no magic byte validation**
- File written to disk **before** DB persistence check — orphaned files on DB write failure
- Weak sanitization regex allows dots (path traversal partial risk)

**Fix:** Add magic byte checks for all allowed extensions. Write file after DB transaction succeeds. Stricter sanitization.

### 1.5 Medium: No CSRF / No Password Policy 🟠

- No CSRF tokens on state-changing endpoints
- No minimum password length or complexity requirements
- No rate limiting on assignment creation or batch compute endpoints

### 1.6 Low: Dependency CVEs 🟢

- `requests==2.31.0` — CVE-2023-32681 (Authorization header leak)
- `redis==5.0.0` — CVE-2023-28858 (URL parsing DoS)
- `docker==7.0.0` in monitoring-service

**Fix:** `pip install --upgrade requests redis docker`

---

## 2. PERFORMANCE & EFFICIENCY — 12 issues (5 CRITICAL, 5 HIGH, 2 MEDIUM)

### 2.1 CRITICAL: Worker OOM Guaranteed 🔴

**Worker `mem_limit: 512m` is insufficient.** Combined ML model memory:
- SBERT all-MiniLM-L12-v2: ~180MB
- RoBERTa chatgpt-detector-roberta: ~500MB
- DistilGPT2: ~350MB
- Python runtime + data: ~200MB
- **Total: ~1.2GB** — exceeds 512m limit by 2.4x

**Fix:** Raise `worker` mem_limit to `2048m` or `3072m` in `docker-compose.yml:106`.

### 2.2 HIGH: Sync DB Calls in Async Handlers 🔴

**All** 27 FastAPI endpoints are `async def` but call synchronous SQLAlchemy functions **directly** — blocking the event loop on every DB query. No `run_in_executor` exists anywhere in the codebase.

**Impact:** Under 5+ concurrent requests, throughput collapses. A 50ms DB query blocks ALL other requests.

**Fix:** Wrap sync DB calls with `run_in_executor`, or migrate to async SQLAlchemy (`sqlalchemy[asyncio]`).

### 2.3 HIGH: Missing DB Indexes 🔴

`get_submissions_by_batch` and `get_similarity_matrix` do **full table scans** on every call as tables grow — no index on `submissions(batch_id)` or `similarity_results(batch_id)`.

**Fix:** Add indexes in `migrate_db()`:
```sql
CREATE INDEX IF NOT EXISTS idx_submissions_batch_id ON submissions(batch_id);
CREATE INDEX IF NOT EXISTS idx_similarity_results_batch_id ON similarity_results(batch_id);
```

### 2.4 HIGH: Application-Side Pagination 🔴

`get_submissions_by_batch` loads **all** rows into memory, then the API slices in Python (line 748: `page = all_subs[offset:offset+limit]`). With 10,000 submissions, every request loads all 10,000 rows.

**Fix:** Use SQL `LIMIT/OFFSET` in the query. Add `limit`/`offset` parameters to `get_submissions_by_batch()`.

### 2.5 MEDIUM: 5 DB Round-Trips per Submission 🟠

In `process_batch_compute`, each submission triggers ~3 DB calls + 1 HTTP notification + 1 file read. For 100 submissions: 300 DB sessions + 100 HTTP calls. Sequential and blocking.

**Fix:** Batch DB writes. Make HTTP notifications fire-and-forget (background thread). Consider concurrent.futures for AI detection.

### 2.6 MEDIUM: Unbounded Redis Key Growth 🟠

Job metadata keys (`job:{job_id}`) and results in Redis are **never expired**. No TTL set. Redis memory grows unbounded.

**Fix:** Add `self._redis.expire(f'job:{job.job_id}', 86400 * 7)` (7-day TTL) after storing.

### 2.7 LOW: Missing Buffer Limits 🟢

- `file.read()` before size check — large file OOMs before validation
- WebSocket `receive_text()` with no timeout — idle connections leak tasks
- `/portal/notify` accepts unbounded JSON payload size

---

## 3. CRASH HANDLING & RESILIENCE — 9 issues (5 HIGH, 3 MEDIUM, 1 LOW)

### 3.1 HIGH: Worker Crash Creates Zombie Jobs 🔴

If the worker process is killed mid-job (OOM, SIGKILL), the job stays `PROCESSING` forever. No watchdog or timeout revives it. **No retry/DLQ mechanism exists.**

**Fix:** Add a watchdog that detects `PROCESSING` jobs older than `max_job_duration`. Implement retry (max 3 attempts) then move to a dead-letter set.

### 3.2 HIGH: No Redis Reconnection 🔴

`QueueClient` and `AsyncQueueClient` have **zero reconnection logic**. If Redis restarts, all queue operations fail permanently until the service restarts.

**Fix:** Implement exponential backoff reconnection in `QueueClient.__init__` and all Redis operation methods.

### 3.3 HIGH: TOCTOU Race Condition on Submission 🔴

`previous_submission` is read in a **separate transaction** from `create_submission`. Two concurrent requests for the same (batch, roll) both see `previous_submission=None`, both create ACTIVE submissions. The file written before DB check can also create orphans.

**Fix:** Move `previous_submission` check INSIDE the `create_submission` transaction. Use `defer` to clean up files on DB failure.

### 3.4 HIGH: Error Leaks to HTTP Response 🔴

`portal_notify` (line 485) returns `detail=str(e)` — raw Python exception strings leak to HTTP responses and are displayed in the frontend UI.

**Fix:** Replace with generic `"Internal server error"`. Log the original exception server-side.

### 3.5 HIGH: No Disk Space Checks 🔴

File uploads and result writes have **zero disk space checks**. `shutil.disk_usage()` is never called. A full disk causes partial file writes and orphaned DB references.

**Fix:** Check `shutil.disk_usage()` before writes; return 507 Insufficient Storage if usage > 95%.

### 3.6 MEDIUM: No Healthchecks on 7 of 9 Services 🟠

Only `postgres` and `redis` have Docker healthchecks. All app services (`api-service`, `worker`, `autoscaler`, `monitoring-service`, `frontend`, `prometheus`, `grafana`) have none.

**Fix:** Add `healthcheck` to each service. For Python services, use `curl --fail http://localhost:8000/health`.

### 3.7 MEDIUM: Unclosed File Handles 🟠

`PdfReader(file_path)` and `Document(file_path)` in `worker.py`, `shared/text_extraction.py`, and `api-service/main.py` are **not used as context managers** — file handles leak until GC.

**Fix:** Use `with open(...)` or context manager patterns for all file I/O.

### 3.8 MEDIUM: `db_ready` Never Retried 🟠

If DB is transiently unavailable at startup, `init_db()` runs once and sets `db_ready=False` forever. No periodic retry.

**Fix:** Add a periodic retry in the startup (or make `db_ready` a property that retries).

---

## 4. UI/UX & FRONTEND — 26 issues (5 CRITICAL, 10 HIGH, 8 MEDIUM, 3 LOW)

### 4.1 CRITICAL: Duplicate Navigation Bars 🔴

`main.jsx` renders `<NavBar />` AND every page component renders its own `.top-nav`. Users see **two stacked nav bars** on every page.

**Fix:** Remove all per-page `.top-nav` elements. Keep only the root `<NavBar />`.

### 4.2 CRITICAL: TeacherDashboard Uses `alert()` 🔴

7 instances of `alert()` — blocks all interaction, unstyled, uncopiable error text.

**Fix:** Replace with inline `.status-box.error` (same pattern as Dashboard.jsx).

### 4.3 CRITICAL: No WebSocket Reconnection 🔴

`useBatchProgress` has no `onclose` handler, no reconnection, no exponential backoff. One disconnect kills progress tracking permanently.

**Fix:** Implement reconnection with exponential backoff (1s → 2s → 4s → ... → 30s max).

### 4.4 CRITICAL: No ARIA / Keyboard Accessibility 🔴

Zero `aria-*` attributes across all 9 components/pages. Screen readers get no information. Matrix cells are not keyboard-accessible. MatrixViewer modal has no focus trap, no Escape key handler.

### 4.5 HIGH: CollusionGraph Hardcoded Canvas Size 🟠

`ForceGraph2D` hardcoded at 600×400px — overflows on mobile, no resize observer.

**Fix:** Use `ResizeObserver` on parent container to dynamically set dimensions.

### 4.6 HIGH: No Loading Spinners 🟠

All loading states use plain text (`"Loading..."`, `"Computing..."`) — no spinners, no skeleton screens.

**Fix:** Create reusable `<Spinner />` component. Add skeleton placeholders for list loading.

### 4.7 HIGH: No Form Validation 🟠

- No email format validation (only `type="email"` browser default)
- No password length/complexity check, no confirmation field
- Assignment name can be submitted empty

### 4.8 HIGH: AI Badge Low Contrast 🟠

AI score badges use `rgba(..., 0.12)` backgrounds — ~2.8:1 contrast ratio, fails WCAG AA (needs 4.5:1).

**Fix:** Use solid hex backgrounds (`#d1fae5`, `#fef3c7`, `#fee2e2`).

### 4.9 MEDIUM: No Toast/Success Messages 🟢

No success feedback after creating assignments, uploading, or computing. AuthPage shows confusing default "Ready" status. No notification system of any kind.

### 4.10 MEDIUM: `/teacher` Route Points to Wrong Component 🟢

Route `/teacher` → `<Dashboard/>` (the main dashboard). `TeacherDashboard.jsx` is never routed — dead code.

### 4.11 LOW: Miscellaneous 🟢

- `App.jsx` is dead code (unused)
- `API_BASE` hardcoded in 7 files
- Dropzone lacks `accept=".pdf,.docx"` attribute
- Static WebSocket URL construction (`.replace("http", "ws")` — fragile)
- Status string-matching (`startsWith('Error')`) fragile
- No 480px phone breakpoint in CSS

---

## 5. FEATURE GAPS — 37 gaps (3 HIGH, 16 MEDIUM, 18 LOW)

### 5.1 HIGH: No External Source Database 🔴

Similarity is intra-batch only. No web/academic paper lookup. The `MOCK_DATABASE` in `shared/plagiarism.py` has 3 entries and is only used by the legacy endpoint. **This is the biggest functional gap** — Turnitin/Copyscape's primary value is the corpus, not the algorithm.

**Effort:** Large (requires external API integration or building a local paper corpus)

### 5.2 HIGH: No RBAC / Authorization Enforcement 🔴

No teacher/student/admin roles. `owner_user_id` stored but never checked. Any authenticated user can access any batch.

**Effort:** Medium

### 5.3 HIGH: JWT in localStorage 🔴

Accepted risk in docs but blocks production deployment. httpOnly cookies needed.

**Effort:** Medium

### 5.4 MEDIUM Gaps (selected) 🟠

| Gap | Effort |
|---|---|
| No cross-batch similarity comparison | Medium |
| No PDF reports (CSV only) | Medium |
| No highlighted similarity passages in viewer | Medium |
| No OCR for scanned documents | Large |
| No email notifications | Medium |
| No aggregate analytics / cheating trends | Medium |
| No assignment deletion/archive | Small |
| No per-assignment similarity threshold config | Small |
| No due dates / late-submission policy | Small |
| No student-facing comparison details | Medium |
| No automated data cleanup / retention policy | Small |
| No audit logging | Medium |
| No CSRF protection | Medium |
| No Alembic migration tool | Medium |
| English-only TF-IDF stop words | Small |

### 5.5 LOW Gaps (selected) 🟢

| Gap | Effort |
|---|---|
| No user profile management | Small |
| No admin/super-user role | Medium |
| No API client/SDK | Medium |
| No responsive/mobile UI | Large |
| No accessibility features | Large |
| No frontend pagination (hardcoded limit=500) | Small |

---

## 6. PRIORITY RANKINGS

### Tier 1 — Fix Immediately (DoD-blocking)

| # | Issue | Category | Effort |
|---|---|---|---|
| 1 | Raise worker `mem_limit` to 2048m+ (OOM guaranteed) | Performance | 1 line |
| 2 | Add auth to all portal endpoints | Security | Medium |
| 3 | Add DB indexes (submissions.batch_id, similarity_results.batch_id) | Performance | Small |
| 4 | Remove duplicate nav bars | UI/UX | Small |
| 5 | Replace `alert()` in TeacherDashboard | UI/UX | Small |
| 6 | Add WebSocket reconnection logic | UI/UX | Small |
| 7 | Fix `portal_notify` error leak | Resilience | 1 line |
| 8 | Fix `create_submission` TOCTOU race | Resilience | Medium |
| 9 | Add Redis reconnection | Resilience | Medium |
| 10 | Fix worker job retry / zombie detection | Resilience | Medium |

### Tier 2 — High Priority (Next Round)

| # | Issue | Category | Effort |
|---|---|---|---|
| 11 | Wrap sync DB calls with `run_in_executor` | Performance | Medium |
| 12 | Add application-side → DB-side pagination | Performance | Small |
| 13 | Add Redis key TTL | Performance | Small |
| 14 | Add disk space checks | Resilience | Small |
| 15 | Add password to Redis | Security | Small |
| 16 | Add JWT env var check (fail hard, not fallback) | Security | Small |
| 17 | Add healthchecks to all services | Resilience | Small |
| 18 | Add AI badge contrast fix | UI/UX | Small |
| 19 | Add loading spinners | UI/UX | Small |
| 20 | Add ARIA labels + keyboard nav | UI/UX | Medium |

### Tier 3 — Medium Priority (Within 2-3 Rounds)

| # | Issue | Category | Effort |
|---|---|---|---|
| 21 | Add RBAC (user roles + authz enforcement) | Security | Medium |
| 22 | Add form validation (email, password, name) | UI/UX | Small |
| 23 | Add toast/success notifications | UI/UX | Medium |
| 24 | Make CollusionGraph responsive | UI/UX | Small |
| 25 | Add TTL on job records | Performance | Small |
| 26 | Move DB files writes after transaction commit | Security | Small |
| 27 | Parallelize AI detection in batch compute | Performance | Small |
| 28 | Add magic byte checks for all file types | Security | Small |
| 29 | Secure Docker socket mounts (dedicated container only) | Security | Small |
| 30 | Pin dependencies to non-vulnerable versions | Security | Small |

### Tier 4 — Future Rounds

| # | Issue | Category | Effort |
|---|---|---|---|
| 31 | Add external source database lookups | Feature | Large |
| 32 | Add PDF reports with highlighted passages | Feature | Medium |
| 33 | Add per-assignment settings (threshold, due date, file types) | Feature | Medium |
| 34 | Add email notifications | Feature | Medium |
| 35 | Add OCR for scanned documents | Feature | Large |
| 36 | Add Alembic migrations | Ops | Medium |
| 37 | Add audit logging | Security | Medium |
| 38 | Add responsive/mobile UI | UI/UX | Large |
| 39 | Add accessibility (a11y) | UI/UX | Large |
| 40 | Add cross-batch similarity comparison | Feature | Medium |

---

## Summary Statistics

| Category | CRITICAL/HIGH | MEDIUM | LOW | **Total** |
|---|---|---|---|---|
| Security | 11 | 9 | 3 | **23** |
| Performance | 6 | 4 | 2 | **12** |
| Resilience | 5 | 3 | 1 | **9** |
| UI/UX | 15 | 8 | 3 | **26** |
| Feature Gaps | 3 | 16 | 18 | **37** |
| **Total** | **40** | **40** | **27** | **107** |

**Estimated effort for Tier 1:** ~1-2 days
**Estimated effort for Tier 1+2:** ~4-5 days
**Estimated effort for Tier 1+2+3:** ~8-10 days
