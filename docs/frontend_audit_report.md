# PlagioScale — Frontend & Feature Audit Report

> Full audit of frontend code, frontend↔backend wiring, and feature gaps vs. industry plagiarism platforms.
> Conducted August 2026. Source: `frontend/src` vs `api-service/main.py` (39 routes) + competitor research (Turnitin, Unicheck, PlagScan, Copyleaks, Quetext, Compilatio, Grammarly).

---

## Part 1 — Code↔Backend Wiring

The backend has 39 routes; every URL the frontend calls exists. The problems are **wiring**, not missing endpoints.

### 🔴 Broken / dead features

| # | Issue | Severity |
|---|---|---|
| B1 | **Download Report PDF button silently does nothing.** `MatrixViewer.jsx` guards on `leftSubmission.submission_id`, but `Dashboard.jsx` `handleCellClick` sets `{ id, label, text }` — never `submission_id`. The button returns early on every click. PDF-report endpoint unreachable from UI. | 🔴 HIGH |
| B2 | **SSE audit tail broken for cookie-only auth.** `AdminPage.jsx` creates `EventSource` without `withCredentials=true`, so the httpOnly cookie (primary auth path) isn't sent cross-origin. Users on the secure path get endless "Waiting for audit events…". | 🔴 HIGH |
| B3 | **`TeacherDashboard.jsx` is 393 lines of dead code.** Never imported in `App.jsx` — `/teacher` routes to the main `Dashboard`. Contains mock snippets, fixed 50-student placeholder, own non-resilient WebSocket, only CSV-export code. | 🟠 MEDIUM |
| B4 | **13 backend endpoints unused by the live UI** (dead surface): `/submit`, `/result/{id}`, `/queue/stats`, `/auth/csrf-token`, `/portal/submissions/{id}/cancel`, `/debug/test-extraction`, `/portal/external-lookup`, `/portal/notify-email`, `/portal/export` (only from orphaned page). | 🟠 MEDIUM |
| B5 | **CollusionGraph node clicks do nothing** — rendered without `onNodeClick`. | 🟢 LOW |
| B6 | **SimilarityMatrix placeholder copy** says "Use *Download CSV* or *compute clusters*" — neither exists in live Dashboard. | 🟢 LOW |
| B7 | **Stale UI copy**: StudentSubmit Dropzone says "`.pdf` and `.docx`" but actually accepts 9 extensions. | 🟢 LOW |
| B8 | **Vite `/api` proxy is dead config** — no code uses the `/api` prefix; all calls go direct to `API_BASE`. | 🟢 LOW |

### ⚠️ UX defects

- `StudentSubmit`/`StudentDashboard` render raw JSON errors (`{"detail":"Invalid access code"}`) as message.
- `StudentDashboard` upload has **no file-size/type validation** (unlike `StudentSubmit`) — server 400s surface as raw JSON.
- `AdminPage` swallows all fetch errors silently — empty stats/users with no explanation.
- `Dashboard` has no loading indicator for detail panel; stale data stays on screen during refresh.
- Filename display relies on `split("_").slice(3)` matching exact server naming scheme — fragile.
- Logged-out NavBar shows "Dashboard"/"My Dashboard" links that bounce to `/auth`.
- Matrix cell click fires 2 sequential text fetches with no per-cell loading state.
- Auth-redirect logic uses fragile string matching on `error.message.includes("authorization"/"token"/"401")`.

---

## Part 2 — Feature Gap Analysis vs. Industry

### Already implemented (matches industry benchmark)

✅ Per-pair similarity matrix · ✅ AI detection scores · ✅ Cross-batch comparison · ✅ Student comparison · ✅ PDF reports (endpoint exists) · ✅ CSV export · ✅ Admin stats + CSV · ✅ Live audit log · ✅ WebSocket live progress · ✅ Blind review · ✅ Collusion graph · ✅ Dark mode · ✅ JWT auth + refresh + CSRF · ✅ Email notifications · ✅ OCR · ✅ External lookup (simulated)

### Top 10 feature gaps (ranked by impact)

| # | Gap | Who has it | Why it matters |
|---|---|---|---|
| F1 | **In-document highlighted matches + clickable source list.** Paper text left, color-coded highlights + "Match Overview" panel right, click match → jump to source. You only show a raw % matrix. | Turnitin, Unicheck, PlagScan, Quetext | This IS the plagiarism report. Without it you can't show *what* matches *where*. |
| F2 | **Color-coded severity bands on scores.** Turnitin: Blue 0 / Green 1-24 / Yellow 25-49 / Orange 50-74 / Red 75-100. Quetext ColorGrade. Grid already red-scales; % badges/scores lack standard severity legend. | Turnitin, Quetext | Instant "is this a problem?" read. |
| F3 | **Exclusion filters with live recalc** (exclude bibliography/quotes/small sources/individual sources → score recomputes). | Turnitin, Unicheck, Compilatio | Drop false positives, see true score. |
| F4 | **Side-by-side source comparison** (paper vs. matched online source, scroll-locked). MatrixViewer compares two *submissions* — no "paper vs. found source" view. | Turnitin, Copyleaks, Quetext, PlagScan | Core proof of copying. |
| F5 | **AI detection caveats / confidence messaging.** Turnitin suppresses AI scores <20% with asterisk; you show AI % unconditionally. | Turnitin, Compilatio | Prevents false accusations; builds trust. |
| F6 | **Student-facing draft self-check** (private, non-indexed pre-submission check). Draft Coach / Studium model. | Turnitin, Compilatio, Grammarly | Reuses engine; huge student value. |
| F7 | **Instructor annotation / feedback layer** (inline comments, QuickMarks libraries, rubrics). | Turnitin Feedback Studio | Turns detection into teaching. |
| F8 | **Threshold filters on matrix** ("only show pairs > 40%") + clustering by similarity so collusion groups visually cluster. | Turnitin, UX best practice | 60×60 matrixes become readable. |
| F9 | **Assignment settings** (due dates, resubmission policy, report visibility, "generate on due date" all-vs-all). | Turnitin, PlagScan | Setup is currently just name + expected count. |
| F10 | **Stylometric authorship verification** (per-student writing fingerprint). | Compilatio, research frontier | Complements AI detection; detects contract cheating. |

### Smaller items
- Analytics dashboard (per-assignment similarity/AI-score distribution charts).
- Empty states with guidance (matrix shows bare "No similarity data").
- Sticky headers / horizontal-scroll affordance on wide submission tables.
- Bulk actions (multi-select submissions).
- Browser extension / in-flow check (Grammarly model).

---

## Part 3 — UX Best Practices to Adopt

### Similarity matrix (data-heavy grid)
- Heatmap + numeric values ✅ (already have).
- Add color-blind-safe palette + **legend**.
- Add **threshold slider** ("only show pairs > X%").
- **Cluster rows/columns by similarity** to reveal collusion groups.
- Triangle split: raw % in one half, classification in the other.

### Loading & status (NN/g)
- Never flip between "No records" and loaded data mid-load.
- Long jobs (compute 10-min cap) need determinate/staged progress, not just "Computing…".
- Empty states must be informational + action-oriented with CTAs.

### Progressive disclosure
- Side panels instead of page navigation for details (Turnitin Match Overview pattern).
- Hide advanced settings behind accordions; never hide what power users need immediately.

---

## Part 4 — Recommended Priority Order

| Round | Scope | Items |
|---|---|---|
| **16** | Bug fixes (cheap, high value) | B1 report button (`submission_id`), B2 SSE `withCredentials`, B3 delete orphaned TeacherDashboard, B6/B7 copy fixes, StudentDashboard upload validation, JSON error parsing |
| **17** | Feature adds | F2 severity bands + legend, F8 threshold slider + clustering, F1 in-document highlight view + source panel, F5 AI confidence caveats |
| **18** | Platform completeness | F6 student draft self-check, F9 assignment settings, F4 side-by-side source comparison, F7 feedback/annotation layer |