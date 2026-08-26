# PlagioScale Frontend — Improvement Opportunities Report

Source: `frontend_plan.md` architecture doc. Findings grouped by severity/category, with concrete fixes.

---

## 1. Security

| # | Issue | Risk | Fix |
|---|---|---|---|
| 1.1 | `getToken()` precedence is **localStorage → cookie**, not cookie → localStorage | Defeats the purpose of the httpOnly cookie being "primary" — any XSS still reads the localStorage token first, since it's checked before falling back to the (inaccessible) cookie | Treat httpOnly cookie as sole source of truth for authenticated requests (`credentials: "include"`); keep localStorage token only for client-side JWT decoding (exp check), not as the value sent in `Authorization` |
| 1.2 | WebSocket auth via `?token={token}` query param | Tokens in URLs leak into server logs, proxy logs, browser history, `Referer` headers | Authenticate via `Sec-WebSocket-Protocol` header or a short-lived, single-use WS ticket issued by `/auth/me` |
| 1.3 | No 401 → silent-refresh-then-retry pattern | Every expired token triggers an immediate logout instead of `refreshToken()` + retry, degrading UX and increasing needless re-logins | Wrap fetch calls in an interceptor: on 401, call `refreshToken()` once, retry the original request, only redirect to `/auth` if refresh also fails |
| 1.4 | Dropzone accepts any file type; extension filtering only exists client-side in `StudentSubmit.jsx` | Inconsistent enforcement across entry points (e.g., `StudentDashboard.jsx` upload form has no listed extension check) | Centralize allowed-extension/size validation in `Dropzone` itself (or a shared `validateFile()` util) so every caller gets it for free; server-side `python-magic` check (already planned in `project_plan.md` 1.3) remains the real boundary |
| 1.5 | `localStorage` XSS exposure already flagged as accepted tech debt | Any XSS (e.g., via a rendered submission filename/text) gets a usable bearer token | Prioritize the planned httpOnly-only migration (`project_plan.md` §4.3) before any non-local deployment; in the meantime, ensure no submission-derived string is ever rendered via `dangerouslySetInnerHTML` |

---

## 2. Auth / Route Protection

| # | Issue | Impact | Fix |
|---|---|---|---|
| 2.1 | No shared `<ProtectedRoute>` / `<RequireAuth>` wrapper — each page (`AdminPage`, `Dashboard`, `StudentDashboard`) reimplements its own auth check | Duplicated logic, easy to introduce inconsistencies (e.g., one page forgets the redirect-on-401 path) | Extract a single `RequireAuth` (and `RequireRole`) route wrapper used in `App.jsx`'s route table |
| 2.2 | `/dashboard`, `/student/dashboard` render UI before the auth check resolves ("no auth required, but still renders a UI") | Flash-of-unauthorized-content: a logged-out user briefly sees dashboard chrome before the redirect fires | Gate initial render behind an auth-resolution loading state, or perform the check in a route loader before mount |
| 2.3 | `AdminPage` calls `fetchMe()` post-mount to check `role === "admin"` | Same FOUC issue — admin-only chrome/data briefly renders for non-admins | Same fix as 2.2, applied via `RequireRole("admin")` |
| 2.4 | `NavBar` reads `getToken()`/`getStoredEmail()` directly from `localStorage` on every render — not reactive | Multi-tab logout/login doesn't update `NavBar` in other tabs until a manual reload; no `storage` event listener | Add a `window.addEventListener('storage', ...)` handler, or lift auth state into a lightweight context (see §4.1) so `NavBar` re-renders on change |

---

## 3. Data Fetching & Loading UX

| # | Issue | Impact | Fix |
|---|---|---|---|
| 3.1 | Compute Similarity uses **both** WebSocket progress *and* a 2s-interval poll (up to 300 attempts / 10 min) | Redundant network traffic; two independent update paths that must agree | Make WS the primary channel; keep polling only as a fallback that activates if no WS message arrives within a timeout window |
| 3.2 | Polling loop has no abort-on-unmount guard described | Risk of `setState` calls after unmount (React warnings, memory leaks) if user navigates away mid-poll | Track an `AbortController`/cancelled ref and stop polling in the effect cleanup |
| 3.3 | Loading states are inconsistent — assignment list has skeletons, but matrix/submissions loads aren't described as having any | Jarring UX: some panels pop in instantly, others blank-then-populate | Apply the same skeleton pattern to matrix and submissions table loads |
| 3.4 | Rename Assignment does an "optimistic local update" with no described rollback on `PUT` failure | UI can show a renamed assignment that the server never persisted | On `PUT` failure, revert the optimistic update and surface the error via `showToast` |
| 3.5 | No shared data-fetching/caching layer — every page independently calls `/portal/assignments`, `fetchMe()`, etc. on mount | Duplicate network calls across page transitions (e.g., `fetchMe()` re-run every time `AdminPage` mounts); no request de-duplication | Introduce a small data layer (TanStack Query / SWR) for caching + de-dup, or at minimum a shared `useCurrentUser()` hook with an in-memory cache |

---

## 4. State Management & Architecture

| # | Issue | Impact | Fix |
|---|---|---|---|
| 4.1 | No context/global store — acceptable for isolated pages, but auth state (`token`, `email`, `role`) is duplicated ad hoc across `NavBar`, `AdminPage`, `Dashboard` | Drift risk between what each component believes the auth state is | A minimal `AuthContext` (just token/email/role + a `refresh()` action) removes the re-read-on-every-render pattern without adopting a full state library |
| 4.2 | `Dashboard.jsx` is 661 lines and owns ~15 pieces of state (assignments, matrix, submissions, rename, delete-confirm, viewer, blind review, etc.) | Hard to test, hard to reason about, high risk of unrelated re-renders | Split into custom hooks: `useAssignments()`, `useAssignmentDetails(batchId)`, `useSimilarityCompute(batchId)`, `useMatrixViewer()`; keep `Dashboard.jsx` as composition only |
| 4.3 | `Dashboard.jsx` is reused for both `/dashboard` and `/teacher`, **and** a separate `TeacherDashboard.jsx` ("legacy/simplified version") also exists per §13 | Ambiguous: is `TeacherDashboard.jsx` dead code, or is it actually routed somewhere not reflected in the routing table? Either way this is a maintenance liability | Confirm actual usage; if unrouted, delete it (consistent with the zero-dead-code cleanup already planned in `project_plan.md` §8); if routed, fix the routing table documentation and consider merging the two into one component with a `simplified` prop |
| 4.4 | `StudentComparison.jsx` derives display filename via `filename.split("_").slice(3).join("_")` | Fragile client-side parsing tied to a specific backend naming convention (`hash_hash_hash_originalname`); breaks silently if the convention changes or the original filename itself contains underscores in the first 3 segments | Have the backend return `original_filename` as a distinct field instead of encoding it into a compound filename string |

---

## 5. WebSocket Hook (`useBatchProgress`)

| # | Issue | Impact | Fix |
|---|---|---|---|
| 5.1 | Exponential backoff caps at 60s and (implicitly) retries forever | No user-visible "give up" state if the socket can never connect (e.g., backend down) — `error` field exists but its surfaced behavior isn't described | Cap total retry duration/count and surface a persistent "live updates unavailable, refresh manually" banner after N failures |
| 5.2 | No client-side heartbeat/ping | Can't distinguish a silently-dead connection from an idle one until the next reconnect attempt | Send periodic pings (or rely on a documented server ping/pong contract) to detect dead sockets faster |

---

## 6. Components

| # | Component | Issue | Fix |
|---|---|---|---|
| 6.1 | `SimilarityMatrix` | Full CSS Grid render for any matrix under the 60×60 preview threshold — e.g., 40×40 = 1,600 focusable/ARIA-labeled cells rendered eagerly | Consider windowing/virtualization (e.g., `react-window`) for matrices above a lower threshold (~20×20), not just the 60×60 cutoff |
| 6.2 | `CollusionGraph` | Nodes/links are derived from the matrix on every render with no memoization mentioned | Wrap the node/link derivation in `useMemo` keyed on `matrix`/`labels`/threshold |
| 6.3 | `MatrixViewer` | Manual focus-trap implementation (Tab/Shift+Tab handling, 100ms auto-focus delay) | Reinventing modal focus management is a common source of subtle bugs (focus escaping, timing races); prefer the native `<dialog>` element or a maintained primitive (e.g., Radix Dialog) |
| 6.4 | `Toast` | All toast types (`success`, `error`, `info`) use `role="alert"` | `role="alert"` is an assertive live region — appropriate for errors, but overly interruptive for routine `success`/`info` toasts for screen reader users | Use `role="status"` (polite) for `success`/`info`, keep `role="alert"` for `error` |
| 6.5 | `NavBar` Tools dropdown | No outside-click dismissal, no `Escape` handling, no `aria-expanded` mentioned | Add outside-click/`Escape` close handlers and `aria-expanded`/`aria-haspopup` attributes |
| 6.6 | Dark mode | Initial theme comes only from `localStorage`, no `prefers-color-scheme` fallback | First-time visitors always get light mode regardless of OS preference; check `window.matchMedia('(prefers-color-scheme: dark)')` when no stored preference exists |

---

## 7. Performance

| # | Issue | Fix |
|---|---|---|
| 7.1 | No route-level code splitting — `AdminPage`, `CollusionGraph` (pulls in `react-force-graph-2d`), and other heavy/rarely-used routes load in the main bundle | Convert route components to `React.lazy` + `Suspense`; lazy-load `CollusionGraph` specifically since it's conditionally rendered (≥3×3 matrix) and not needed on first paint |
| 7.2 | No general memoization strategy beyond one `useMemo` for blind-review label remapping | Audit `Dashboard.jsx` (post-split per §4.2) for derived values recomputed every render (e.g., sorted assignment lists) and memoize where the input is stable |

---

## 8. Testing Gaps

Current coverage: 30 frontend tests total (`auth.test.js` ×6, `authFetch.test.js` ×5, `App.test.jsx` ×1, `BlindReviewToggle.test.jsx` ×3, `websocket.test.js` ×9, `AuthGuards.test.jsx` ×6).

| Untested surface | Why it matters |
|---|---|
| `Dashboard.jsx` (661 lines, most complex page) | Highest bug-risk surface in the app; zero direct test coverage |
| `useBatchProgress` (WebSocket hook) | Reconnection/backoff logic is exactly the kind of thing that silently regresses without tests |
| `AdminPage` | Role-gating logic (§2.3) is security-relevant and untested |
| `StudentSubmit`, `StudentDashboard` | Core user-facing upload flows, no coverage |
| `CrossBatchPage`, `StudentComparison` | No coverage |
| `SimilarityMatrix`, `MatrixViewer`, `CollusionGraph` | No coverage of interaction (cell click → viewer open) or accessibility roles |
| End-to-end flow (login → create assignment → upload → compute → view matrix) | No Playwright/Cypress suite exists despite this being the core product flow |

**Recommendation:** prioritize tests for `useBatchProgress` and the auth-guard logic first (highest risk-to-effort ratio), then an E2E happy-path test before adding exhaustive component coverage.

---

## 9. Build / CI Correctness Risk

From the CI work-state notes appended to the frontend doc:

> CI installs `requirementsall.txt` — `bcrypt`, `python-jose[cryptography]`, `email-validator` missing for api-service; **mocks in `conftest.py` handle this.**

This is a correctness risk, not just a test-hygiene issue: if these packages are genuinely absent from `requirementsall.txt`, the tests are mocking around a dependency that may not exist in the actual runtime container, meaning `pytest` could pass while the real `api-service` fails to import at startup. **Fix:** add the three packages to `requirementsall.txt` and remove the corresponding mocks, so tests exercise the real import path.

---

## 10. Priority Summary

| Priority | Items |
|---|---|
| **High** | 1.1 (token precedence), 1.2 (WS token in URL), 2.1/2.2/2.3 (route protection + FOUC), 9 (CI masking missing deps) |
| **Medium** | 1.3 (401 refresh-retry), 3.1/3.2 (redundant polling + abort), 4.2 (Dashboard decomposition), 4.3 (dead/duplicate TeacherDashboard), 8 (Dashboard + WS hook tests) |
| **Low** | 6.4/6.5/6.6 (a11y polish), 7.1/7.2 (perf), 6.1/6.3 (virtualization, focus-trap library swap) |