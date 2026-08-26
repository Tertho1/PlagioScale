# PlagioScale Frontend — Complete Architecture & Design Report

## 1. Project Overview

**Stack:** React 18 + Vite 8 + react-router-dom v6. No state management library (pure `useState`/`useEffect`). No TypeScript — plain JSX with `PropTypes` runtime validation.

**Build tooling:** Vite with `@vitejs/plugin-react`, ESBuild with automatic JSX runtime. Dev server proxies `/api` → `http://localhost:8000` (configurable via `VITE_API_BASE` env var). Vitest for testing with jsdom environment.

**File layout:**
```
src/
  main.jsx              # Entry — mounts <BrowserRouter><App /></BrowserRouter>
  App.jsx               # Root: NavBar, ToastContainer, Routes
  index.css             # CSS reset, body base styles
  styles/portal.css     # 1440-line design system (all visual styles + dark mode)
  pages/                # 8 route-level page components
  components/           # 7 reusable UI components
  utils/                # auth.js (JWT/cookie/CSRF), websocket.js (WS hook)
  tests/                # 6 test files + setup.js
```

---

## 2. Entry Point (`main.jsx`)

```jsx
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter><App /></BrowserRouter>
  </React.StrictMode>
)
```

Wraps everything in `BrowserRouter` for client-side routing. No context providers, no global state store — all state lives in individual components via `useState`.

---

## 3. Routing & App Shell (`App.jsx`)

### Routes defined:

| Path | Component | Auth Required |
|---|---|---|
| `/` | Home | No |
| `/auth` | AuthPage | No (redirects to /dashboard if token exists) |
| `/dashboard` | Dashboard | No (redirects to /auth if no token, but still renders a UI) |
| `/student` | StudentSubmit | No |
| `/teacher` | Dashboard (same as /dashboard) | No |
| `/student/dashboard` | StudentDashboard | No (but checks auth headers) |
| `/admin` | AdminPage | Yes (checks role === "admin" via fetchMe) |
| `/cross-batch` | CrossBatchPage | No |
| `/student/comparison/:submissionId` | StudentComparison | No |

### App shell structure:
```
<>
  <a href="#main-content" className="skip-link" />
  <div className="root-shell">
    <NavBar />
    <ToastContainer />
    <Routes>…</Routes>
  </div>
</>
```

---

## 4. Navigation Bar (NavBar in `App.jsx`)

### Auth-aware link rendering

`NavBar` is defined inside `App.jsx` (not a separate component). It reads `getToken()` and `getStoredEmail()` on EVERY render (no reactivity — these are direct `localStorage` reads).

**When not logged in (no token):**
```
[PlagioScale]  Home  Submit  Login / Sign up  Dashboard  My Dashboard
```

**When logged in (token exists):**
```
[PlagioScale]  Home  Submit  Dashboard  My Dashboard  Cross-Batch  [Tools ▼]  {email}  🌙  [Logout]
```

- The `Login / Sign up` link is replaced by the email + Logout button.
- `Tools` is a dropdown button with links to external monitoring services (Monitor:8090, Grafana:3000, Prometheus:9090). It opens absolutely positioned below the button on click. Implemented via `useState(showTools)` — no outside-click handling.
- Dark mode toggle: `🌙` / `☀️` button. Reads initial state from `localStorage.getItem('theme') === 'dark'`. On toggle, sets `document.documentElement.setAttribute('data-theme', …)` and persists to `localStorage`.
- `nav-email` shows the stored email in dimmed text.

### Logout behavior

```jsx
onClick={() => { clearToken(); window.location.href = '/' }}
```

`clearToken()` in `auth.js`:
1. Removes `plagioscale_access_token` and `plagioscale_user_email` from `localStorage`
2. Deletes `access_token` and `csrf_token` cookies via `document.cookie`
3. Fires a background `POST /auth/logout` with `credentials: "include"` (fire-and-forget, `.catch(() => {})`)
4. Sets `refreshPromise = null`

Then a full `window.location.href = '/'` reload, which re-renders the entire SPA from scratch.

---

## 5. Authentication System (`src/utils/auth.js`)

### Token storage: dual-path design

**Primary path (secure):** httpOnly cookies (`access_token`, `csrf_token`) set by the server on login. These are inaccessible to JavaScript — protection against XSS.

**Fallback path (localStorage):** `plagioscale_access_token` and `plagioscale_user_email` keys. Used for:
- Client-side JWT decoding (to check expiration)
- Building `Authorization: Bearer <token>` headers for API calls
- Cross-tab/window persistence

### Key functions:

**`getToken()`:**
```js
return localStorage.getItem(TOKEN_KEY) || getCookie("access_token") || ""
```
Precedence: localStorage → cookie → empty string.

**`getStoredEmail()`:** Reads `plagioscale_user_email` from localStorage.

**`setToken(token, email)`:** Stores token + email in localStorage, resets `refreshPromise = null`.

**`clearToken()`:** Removes localStorage keys, deletes cookies, fire-and-forget POST to `/auth/logout`.

**`isTokenExpired(token)`:** Decodes JWT payload via `atob` on the second dot-separated segment. Compares `payload.exp * 1000` with `Date.now()`. Returns `true` if no valid `exp` field.

### HTTP header construction:

**`getAuthHeaders()` (async):**
```js
const token = getToken();
const csrf = getCookie("csrf_token");
const headers = {};
if (token && !isTokenExpired(token)) headers["Authorization"] = `Bearer ${token}`;
if (csrf) headers["X-CSRF-Token"] = csrf;
return headers;
```

**`fetchOpts(opts)`:** Same logic but merges with user-provided options.

### Token refresh:

**`refreshToken()` (async with deduplication):**
- Uses a module-level `refreshPromise` variable to prevent concurrent refresh calls.
- POST to `/auth/refresh` with credentials and optional Bearer token.
- On success, stores new token via `setToken()` and returns it.
- On failure, calls `clearToken()` and returns `null`.

**`fetchMe()`:** Simple fetch to `/auth/me` with credentials. Returns user object or null.

---

## 6. Auth Page (`AuthPage.jsx`)

### Two modes: `login` (default) and `signup`

Toggled by a button at the bottom: "Need an account?" / "Already have an account?"

### Form fields:

| Mode | Fields |
|---|---|
| login | Email, Password |
| signup | Email, Name, Password |

### Validation (client-side before API call):
1. Email must match `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`
2. Password must be ≥ 6 characters
3. Name required in signup mode

### API call:
```
POST /auth/login  → { email, password }
POST /auth/signup → { email, name, password }
```
Response expected: `{ access_token: "…" }`

On success: `setToken(data.access_token, email)` + navigate to `/dashboard`.
On error: `clearToken()` + show error message.

### Redirect on mount:
```jsx
useEffect(() => {
  if (getToken()) navigate("/dashboard");
}, []);
```

### Layout:
Two-column grid (`dashboard-layout`):
- **Left:** Form card with the sign-in/sign-up form
- **Right:** Guide card showing "What this unlocks" (list of 3 steps)

---

## 7. Dashboard (`Dashboard.jsx`) — The Main Workspace

This is the most complex page (661 lines). It's reused for both `/dashboard` and `/teacher` routes.

### State variables (extensive):

| State | Purpose |
|---|---|
| `loading` | Initial assignment list loading |
| `error` | Error message display |
| `assignmentName`, `expectedCount` | Create-assignment form fields |
| `ownedAssignments`, `sharedAssignments` | Two lists from `/portal/assignments` |
| `selectedId` | Currently selected batch ID (from URL search param `?batch=`) |
| `selected` | Full assignment object for the selected batch |
| `matrix`, `matrixIds`, `labels` | Similarity matrix data + row labels |
| `submissions` | List of submissions for selected batch |
| `creating`, `refreshing`, `computing` | Loading flags for async ops |
| `renaming`, `saving`, `renameValue` | Inline rename state |
| `confirmDelete`, `deleting` | Delete confirmation modal state |
| `viewer` | MatrixViewer modal: `{ open, left, right, similarity }` |
| `blindReview` | Boolean toggle |

### Data loading flow:

**On mount (if token exists, not expired):**
```
useEffect → loadAssignments()
```

**`loadAssignments()`:**
1. `GET /portal/assignments` with auth headers
2. Response: `{ owned: […], shared: […] }`
3. Sorts both lists by `created_at` descending
4. Sets first assignment as `selectedId` if none is URL-specified
5. On 401/authorization errors → `clearToken()` + `navigate("/auth")`

**When `selectedId` changes:**
```
useEffect → loadAssignmentDetails(selectedId)
```

**`loadAssignmentDetails(batchId)`:**
1. `GET /portal/assignments/{batchId}` → sets `selected` and `submissions`
2. `GET /portal/similarity-matrix/{batchId}` → parses matrix object into 2D array
3. `GET /portal/submissions/{batchId}?limit=500&offset=0` → builds label map (roll numbers)
4. Error on 401 → redirect to auth

### WebSocket progress:

`useBatchProgress(selectedId)` hook returns `{ processed, total, error }`. When `processed` changes, auto-refreshes assignment details.

### Actions:

**Create Assignment:**
1. `POST /portal/assignments` with `{ name, expected_count }`
2. Reload assignments list
3. Select and load the new batch

**Compute Similarity:**
1. `POST /portal/compute-similarity/{selectedId}` → returns `job_id`
2. **Polling loop:** Every 2 seconds, `GET /status/{jobId}`, up to 300 attempts (10 minutes)
3. On COMPLETED → refresh assignment details
4. On FAILED/timeout → show error

**Rename Assignment:**
1. Inline editing — clicking "Rename" shows an input field replacing the title
2. Enter to save, Escape to cancel
3. `PUT /portal/assignments/{selectedId}` with `{ name }`
4. Optimistic local update

**Delete Assignment:**
1. Confirmation modal: type the assignment name to enable the delete button
2. `DELETE /portal/assignments/{selectedId}`
3. Clears local state and reloads

**Cell Click (matrix):**
1. Determines `leftId` and `rightId` from `matrixIds`
2. Fetches text for both submissions
3. Opens MatrixViewer modal

### Layout:

Two-column grid (`dashboard-grid`):
- **Left panel** (`dashboard-panel-list`): Create-assignment form, owned/shared assignment lists (clickable cards, skeleton loading, active card highlighted)
- **Right panel** (`dashboard-panel-detail`): Assignment header (rename, delete, blind review, refresh, compute buttons), stats cards (Access Code, Expected count, Submitted count), submissions table, SimilarityMatrix, CollusionGraph (≥3 submissions)

---

## 8. Student Dashboard (`StudentDashboard.jsx`)

**Data flow:** `GET /portal/my` → `{ batches: [{ batch_id, name, submissions: […] }] }`

**Upload form:** Batch selector, Roll (required), Name (optional), File via Dropzone. `POST /portal/submit` with FormData.

**Submissions history table per batch:** Roll, File, Status, Score, Submitted date, Details link → `/student/comparison/{submissionId}`.

---

## 9. Student Submit (`StudentSubmit.jsx`)

Anonymous/public submission page (no auth required). Persists name/email/roll in localStorage across visits.

**Form fields:** Roll (required), Access Code (required), Name (optional, remembered), Email (optional, remembered), File via Dropzone.

**Validation:** Roll + access code non-empty, file required, max 10MB, allowed extensions: `.pdf .docx .txt .md .csv .py .java .js .ts`.

**Submission:** `POST /portal/submit` → FormData `{ file, roll, name, email, access_code }`.

---

## 10. Admin Page (`AdminPage.jsx`)

Requires `role === "admin"` — verified on mount via `fetchMe()`.

### Tabs (4):

**Stats tab:** `GET /admin/stats` → key-value table, Refresh/Export CSV buttons.

**Users tab:** Search by email/name (debounced), paginated table (20 per page), role selector dropdown with direct `POST /admin/users/{userId}/role`.

**Notifications tab:** Pending count from stats, "Send Pending Notifications" button → `POST /admin/notifications/send`.

**Audit tab:** `EventSource` (SSE) to `/admin/audit/tail?token={token}`, live-scrolling monospace log (max 200 entries), auto-reconnects.

---

## 11. Cross-Batch Page (`CrossBatchPage.jsx`)

Loads all assignments, two dropdown selectors for Batch 1/Batch 2, "Compare" button → `GET /portal/cross-batch/{batch1}/{batch2}`, results table with similarity color badges.

---

## 12. Student Comparison Page (`StudentComparison.jsx`)

Route: `/student/comparison/:submissionId`. Fetches `GET /portal/student-comparison/{submissionId}`, shows overall score with badge, pairwise comparison table.

---

## 13. Teacher Dashboard (`TeacherDashboard.jsx`)

Legacy/simplified Dashboard. Creates batch via `POST /portal/assignments`, WebSocket progress, poll-based compute + matrix fetch, SimilarityMatrix + MatrixViewer (mock data), Export CSV. Auth-gated (shows sign-in prompt if no token).

---

## 14. Components

### BlindReviewToggle (`BlindReviewToggle.jsx`)
Checkbox toggle with custom slider UI. Flips `blindReview` state → `useMemo` remaps labels to "Submission N".

### CollusionGraph (`CollusionGraph.jsx`)
Uses `react-force-graph-2d`. Nodes from labels, links from matrix cells ≥ 0.5. Link color: `rgba(220, 38, 38, score)`. Responsive via `ResizeObserver`. Requires ≥ 3 submissions.

### Dropzone (`Dropzone.jsx`)
Drag-and-drop + click-to-choose. Visual hover state (`is-hovered` CSS class). Accepts any file type (parent filters).

### MatrixViewer (`MatrixViewer.jsx`)
Modal dialog with side-by-side comparison. Shows Roll/Name/File, monospace `<pre>` blocks (blue-tinted left, purple-tinted right), similarity score, "Download Report" button. Keyboard accessible: focus trap, Escape to close, Enter/Space to trigger.

### SimilarityMatrix (`SimilarityMatrix.jsx`) + CSS
CSS Grid of colored cells. Color scale: `rgb(255*v, 200*(1-v), 100*(1-v))` — white (0) → red (1). Diagonal shows "—". Title/aria-label on each cell. Click/keyboard (Enter/Space) calls `onCellClick`. Preview mode for matrices > 60×60.

### Toast (`Toast.jsx`)
Global pub/sub notification system (module-level `Set` of listeners). `showToast(message, type, duration)`. Types: success (green), error (red), info (blue). Auto-dismiss (default 4s), click to dismiss. Fixed top-right, slide-in animation, max-width 360px.

---

## 15. WebSocket Hook (`src/utils/websocket.js`)

### `useBatchProgress(batchId)` hook

**Connection:** `ws://{API_BASE.replace("http", "ws")}/portal/ws/{batchId}?token={token}`

**Reconnection:** Exponential backoff (base 2s, double, max 60s), cancelled via `cancelledRef`, retry counter resets on successful open.

**Message handling:** Parses JSON `{ processed, total }`, updates progress state. Ignores non-JSON (pings).

**Cleanup:** Sets `cancelledRef = true`, closes WebSocket on unmount/batchId change. New batchId → fresh connection.

---

## 16. CSS & Theming (`styles/portal.css`, 1440 lines)

### Design tokens (CSS custom properties):

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#f3f7ff` | `#0f172a` |
| `--surface` | `rgba(255,255,255,0.88)` | `rgba(30,41,59,0.88)` |
| `--text` | `#0f172a` | `#f1f5f9` |
| `--text-soft` | `#475569` | `#94a3b8` |
| `--accent` | `#2563eb` | `#60a5fa` |
| `--border` | `rgba(148,163,184,0.25)` | `rgba(100,116,139,0.25)` |
| `--shadow` | `0 24px 70px rgba(15,23,42,0.12)` | `0 24px 70px rgba(0,0,0,0.4)` |

### Dark mode:
Activated by `[data-theme="dark"]` on `<html>`. All colors swap to dark variants. Toggled by NavBar moon/sun button. Persisted in `localStorage.getItem('theme')`.

### Visual style:
- **Background:** Radial gradients (blue top-left, purple top-right) + subtle grid pattern overlay
- **Cards:** Frosted glass (`backdrop-filter: blur(12px)`), semi-transparent `rgba`, rounded corners (14px–28px)
- **Buttons:** Gradient accent (blue→purple) for primary, white + border for secondary, dashed-border for ghost
- **Transitions:** Hover `translateY(-1px)` lift, focus ring shadows
- **Typography:** Inter / system-ui font stack, headings clamped with `clamp()`

### Responsive:
Breakpoints at 980px, 768px, 640px. Grids collapse to single column, navigation stacks vertically.

### Accessibility:
- `skip-link` (hidden until focused)
- `*:focus-visible` blue outline
- `role="grid"`, `role="gridcell"`, `aria-label` on matrix cells
- `role="dialog"`, `aria-modal="true"` on modals
- Toast has `role="alert"`

---

## 17. Testing (`src/tests/`)

| File | Tests | What it covers |
|---|---|---|
| `auth.test.js` | 6 | Token roundtrip, getAuthHeaders, clearToken, refreshToken |
| `authFetch.test.js` | 5 | Auth headers, 401 refresh-retry, redirect on failure, caller headers |
| `App.test.jsx` | 1 | App renders PlagioScale text |
| `BlindReviewToggle.test.jsx` | 3 | Renders, toggle callback, respects enabled prop |
| `websocket.test.js` | 9 | useBatchProgress: connect, open, message, close, retry, backoff, max retries, unmount |
| `AuthGuards.test.jsx` | 6 | RequireAuth: auth/loading/redirect; RequireRole: match/mismatch/redirect |

Setup: `setup.js` imports `@testing-library/jest-dom`. Vitest with jsdom environment, globals enabled.

---

## 18. State Management Patterns

No React Context, no Redux, no Zustand. Every page is fully self-contained with `useState`:

- **Per-component state:** Each page declares its own `useState` hooks.
- **Sibling communication:** None — pages don't share mutable state.
- **Auth state:** Read from `localStorage` via `getToken()` on each render. Not reactive — components re-read on mount or on `window.location` reload.
- **Toast notifications:** Pub/sub via module-level `Set` of listener callbacks. No context.
- **Data fetching:** Each page calls its own API endpoints on mount and on user actions. No data cache layer.

**Key observation:** After login, `navigate("/dashboard")` triggers a re-render, at which point `getToken()` returns the newly stored token. After logout, `window.location.href = '/'` does a full reload.

---

## 19. API Communication Pattern

All API calls use:
1. `credentials: "include"` (sends httpOnly cookies)
2. `Authorization: Bearer {token}` header from `getAuthHeaders()` (localStorage path)
3. `X-CSRF-Token` header from cookie (CSRF protection)

`API_BASE` = `import.meta.env.VITE_API_BASE || 'http://localhost:8000'`. In Docker/production, the Vite dev proxy at `/api` → backend is used.
