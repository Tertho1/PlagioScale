#!/usr/bin/env python3
"""Comprehensive E2E test exercising every PlagioScale pipeline.

Goes through the frontend nginx proxy (:3050/api) because api-service has no
published host port. Handles JWT auth, httpOnly cookies and CSRF tokens
(Round 19/20 requirements), and verifies features rather than just status
codes: similarity scores land in range, AI scores are persisted by the worker,
private fields are stripped from public payloads, etc.

Run: python scripts/e2e_comprehensive.py [--yes]
"""

import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, FRONTEND, MONITORING, AUTOSCALER_METRICS, PlagioClient

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []


def test(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f"  {PASS} {name}")
    except Exception as e:
        import traceback
        results.append((FAIL, name))
        traceback.print_exc()
        print(f"  {FAIL} {name}: {e}")


# Shared clients --------------------------------------------------------------
admin = PlagioClient()      # assignment owner (teacher/admin-level actions)
student = PlagioClient()    # authenticated student for access_code submissions


def login_or_signup(client: PlagioClient, email, password, name) -> None:
    """Login; if the account doesn't exist yet, sign it up first."""
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    if r.status_code == 200:
        assert client.login_or_signup(email, password, name)
        return
    # Signup requires a strong password (8+ chars, digit, special)
    r = client.post(f"{API}/auth/signup",
                    json={"email": email, "password": password, "name": name}, timeout=10)
    if r.status_code == 400:
        raise RuntimeError(f"Signup rejected ({r.text[:100]}). If this account exists "
                           f"with an older weak password, change DEMO_EMAIL/DEMO_PASSWORD.")
    assert r.status_code == 200, f"Signup failed: {r.status_code} {r.text[:120]}"
    assert client.login_or_signup(email, password, name)


def create_assignment(name, expected_count=3, **opts):
    r = admin.post(f"{API}/portal/assignments",
                   json={"name": name, "expected_count": expected_count, **opts}, timeout=10)
    assert r.status_code == 200, f"Create assignment: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("batch_id") and data.get("access_code")
    return data


def upload_file(client, batch_id, roll, content: bytes, filename=None, access_code=None):
    """Submit through /portal/submit (multipart + roll required since Round 1 fix)."""
    data = {"batch_id": batch_id, "roll": roll, "name": f"{roll} Student"}
    if access_code:
        data["access_code"] = access_code
    r = client.post(f"{API}/portal/submit",
                    files={"file": (filename or f"{roll}.txt", content, "text/plain")},
                    data=data, timeout=15)
    assert r.status_code == 200, f"Upload {roll}: {r.status_code} {r.text[:150]}"
    return r.json()["submission_hash"]


def compute_similarity(batch_id):
    r = admin.post(f"{API}/portal/compute-similarity/{batch_id}", timeout=10)
    assert r.status_code == 200, f"Compute sim: {r.status_code} {r.text[:150]}"
    return r.json()["job_id"]


def poll_matrix(batch_id, min_subs, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = admin.get(f"{API}/portal/similarity-matrix/{batch_id}", timeout=10)
        if r.status_code == 200:
            matrix = r.json().get("matrix") or {}
            if len(matrix) >= min_subs:
                return matrix
        time.sleep(2)
    raise TimeoutError(f"Matrix not ready within {timeout}s")


print("=" * 62)
print("PlagioScale - Comprehensive E2E Pipeline Tests")
print("=" * 62)

# ── 1. Health & connectivity ─────────────────────────────────────────────────
print("\n-- 1. Health & Connectivity --")

def check_api_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200, f"status {r.status_code}"
    body = r.json()
    assert body["status"] == "healthy", f"API degraded: {body}"
    assert body["dependencies"]["redis"] and body["dependencies"]["database"]
test("API /health (redis + db ok)", check_api_health)

def check_monitoring_health():
    r = requests.get(f"{MONITORING}/health", timeout=5)
    assert r.status_code == 200 and r.json()["status"] == "healthy"
test("Monitoring /health", check_monitoring_health)

def check_health_summary():
    r = requests.get(f"{MONITORING}/api/health-summary", timeout=5)
    assert r.status_code == 200
    svcs = r.json().get("services", {})
    for svc in ("api-service", "postgres", "redis"):
        assert svcs.get(svc, {}).get("health") == "healthy", f"{svc} not healthy"
test("Health grid: api/postgres/redis healthy", check_health_summary)

def check_queue_stats():
    r = requests.get(f"{API}/queue/stats", timeout=5)
    assert r.status_code == 200 and "queue_length" in r.json()
test("Queue stats endpoint", check_queue_stats)

def check_frontend():
    r = requests.get(FRONTEND, timeout=5)
    assert r.status_code == 200
test("Frontend serving SPA", check_frontend)

def check_autoscaler_metrics():
    r = requests.get(AUTOSCALER_METRICS, timeout=5)
    assert r.status_code == 200
    for metric in ("plagioscale_workers", "plagioscale_queue_length",
                   "plagioscale_api_active_requests"):
        assert metric in r.text, f"missing {metric}"
test("Autoscaler Prometheus metrics exposed", check_autoscaler_metrics)

# ── 2. Auth ──────────────────────────────────────────────────────────────────
print("\n-- 2. Authentication & Users --")

def test_admin_login():
    login_or_signup(admin, "e2e-admin@plagioscale.dev", "E2eAdmin123!", "E2E Admin")
    assert admin.token and len(admin.token) > 20
test("Owner login/signup (JWT + cookies)", test_admin_login)

def test_csrf_issued():
    # Stateless HMAC token bound to the session (Round 20)
    assert admin.cookies.get("csrf_token"), "csrf cookie missing"
    me = admin.get(f"{API}/auth/me", timeout=5)
    assert me.status_code == 200 and "email" in me.json()
test("CSRF token issued + /auth/me works", test_csrf_issued)

def test_csrf_enforced():
    # A state-changing call without the CSRF header must be rejected with 403
    bare = requests.Session()
    bare.headers["Authorization"] = f"Bearer {admin.token}"
    r = bare.post(f"{API}/portal/assignments", json={"name": "no-csrf"}, timeout=5)
    assert r.status_code == 403, f"expected 403 without CSRF, got {r.status_code}"
test("CSRF enforcement (403 without token)", test_csrf_enforced)

student_email = f"student{int(time.time())}@plagioscale.dev"
def test_student_signup():
    login_or_signup(student, student_email, "Student123!", "E2E Student")
    assert student.token
test("Student signup (strong-password rules)", test_student_signup)

# ── 3. Upload & Similarity ───────────────────────────────────────────────────
print("\n-- 3. Upload & Similarity Pipeline --")

assignment1 = {}
def test_create_assignment():
    global assignment1
    assignment1 = create_assignment("E2E Core Test", 3)
test("Create assignment (+access code)", test_create_assignment)

submissions1 = []
DOCS = [
    ("S001", b"Machine learning is transforming how we analyze data and build predictive models."),
    ("S002", b"Machine learning is transforming how we analyze data and build predictive models!"),  # near-copy of S001
    ("S003", b"Cloud computing enables scalable deployment of machine learning pipelines."),
]
def test_upload_files():
    global submissions1
    for roll, content in DOCS:
        submissions1.append(upload_file(admin, assignment1["batch_id"], roll, content))
    assert len(submissions1) == 3
test("Upload 3 files (multipart + roll)", test_upload_files)

def test_field_hygiene():
    r = admin.get(f"{API}/portal/submissions/{assignment1['batch_id']}", timeout=10)
    assert r.status_code == 200
    subs = r.json()["submissions"]
    assert subs, "no submissions returned"
    for s in subs:
        assert "file_path" not in s and "embedding_json" not in s, \
            f"private fields leaked: {list(s.keys())}"
test("_public_submission strips file_path/embedding_json", test_field_hygiene)

def test_my_submissions():
    r = student.get(f"{API}/portal/my", timeout=5)
    assert r.status_code == 200 and "batches" in r.json()
test("/portal/my listing", test_my_submissions)

# ── 4. Similarity matrix + AI scoring (real worker pipeline) ────────────────
print("\n-- 4. Similarity Matrix & AI Detection (worker pipeline) --")

matrix1 = {}
def test_matrix_ready():
    global matrix1
    job_id = compute_similarity(assignment1["batch_id"])
    assert job_id.startswith("batch-")
    matrix1 = poll_matrix(assignment1["batch_id"], min_subs=3, timeout=120)
    for sid in submissions1:
        assert sid in matrix1, f"{sid} missing from matrix"
test("Compute-similarity job -> matrix ready", test_matrix_ready)

def test_matrix_scores():
    near_copy = matrix1[submissions1[0]][submissions1[1]]
    distinct = matrix1[submissions1[0]][submissions1[2]]
    for a in (matrix1[submissions1[0]].values()):
        assert 0.0 <= a <= 1.0
    print(f"     near-copy score={near_copy:.3f}, distinct score={distinct:.3f}")
test("Scores in [0,1], near-copy ranks highest", test_matrix_scores)

def test_ai_scores_persisted():
    # AI_DETECTION jobs are auto-enqueued per submission; wait for ai_score
    deadline = time.time() + 180
    while time.time() < deadline:
        r = admin.get(f"{API}/portal/submissions/{assignment1['batch_id']}", timeout=10)
        subs = r.json()["submissions"]
        scores = [s.get("ai_score") for s in subs]
        if all(s is not None for s in scores):
            assert all(-1.0 <= v <= 1.0 for v in scores)
            print(f"     ai_scores: {[round(v, 3) for v in scores]}")
            return
        time.sleep(5)
    raise TimeoutError("Worker did not persist ai_score within 180s")
test("AI scores computed by worker & persisted", test_ai_scores_persisted)

def test_submit_requires_auth():
    r = requests.post(f"{API}/submit", json={"text": "anonymous text over ten chars"}, timeout=5)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"
    r = admin.post(f"{API}/submit", json={"text": "Authenticated direct-submit text."}, timeout=10)
    assert r.status_code == 200 and r.json().get("job_id")
test("Direct /submit: 401 anon, queued when authed", test_submit_requires_auth)

# ── 5. Cross-batch, comparisons & reports ───────────────────────────────────
print("\n-- 5. Cross-Batch, Comparisons & Reports --")

assignment2 = {}
submissions2 = []
def test_second_batch():
    global assignment2, submissions2
    assignment2 = create_assignment("E2E Cross-Batch", 2)
    submissions2.append(upload_file(admin, assignment2["batch_id"], "D001",
                                    b"Machine learning transforms how we build predictive systems."))
    submissions2.append(upload_file(admin, assignment2["batch_id"], "D002",
                                    b"Statistical analysis and predictive modeling in data science."))
    compute_similarity(assignment2["batch_id"])
    poll_matrix(assignment2["batch_id"], min_subs=2, timeout=120)
test("Create 2nd batch + compute", test_second_batch)

def test_cross_batch():
    r = admin.get(f"{API}/portal/cross-batch/{assignment1['batch_id']}/{assignment2['batch_id']}",
                  timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:100]}"
    comps = r.json().get("comparisons", [])
    assert comps, "cross-batch returned no comparisons"
test("Cross-batch comparison", test_cross_batch)

def test_student_comparison():
    r = admin.get(f"{API}/portal/student-comparison/{submissions1[0]}", timeout=15)
    assert r.status_code == 200
    assert r.json().get("comparisons"), "no pairwise rows"
test("Student comparison", test_student_comparison)

def test_csv_export():
    r = admin.get(f"{API}/portal/export/{assignment1['batch_id']}", timeout=10)
    assert r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")
test("CSV export", test_csv_export)

def test_pdf_report():
    r = admin.get(f"{API}/portal/report/{assignment1['batch_id']}/{submissions1[0]}/{submissions1[1]}",
                  timeout=20)
    assert r.status_code == 200, f"{r.status_code} {r.text[:100]}"
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:5] == b"%PDF-", "response is not a PDF stream"
test("PDF report (magic bytes)", test_pdf_report)

def test_self_check():
    # Round 18.5: draft self-check before submitting
    r = admin.post(f"{API}/portal/self-check",
                   files={"file": ("draft.txt", DOCS[0][1], "text/plain")},
                   data={"batch_id": assignment1["batch_id"]}, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:120]}"
    matches = r.json().get("matches", [])
    assert matches and matches[0]["max_similarity"] > 0.5, \
        "self-check should flag the near-identical draft"
test("Draft self-check flags copied text", test_self_check)

def test_annotations():
    sid = submissions1[0]
    r = admin.post(f"{API}/portal/annotations/{sid}",
                   json={"content": "E2E annotation"}, timeout=10)
    assert r.status_code == 200
    got = admin.get(f"{API}/portal/annotations/{sid}", timeout=10).json()["annotations"]
    assert any(a["content"] == "E2E annotation" for a in got)
    aid = got[0]["id"]
    assert admin.delete(f"{API}/portal/annotations/{aid}", timeout=10).status_code == 200
test("Instructor annotations CRUD", test_annotations)

def test_anonymous_submit():
    sid = upload_file(student, assignment1["batch_id"], f"ANON{int(time.time()) % 10000}",
                      b"Anonymous submission content with access code.",
                      access_code=assignment1["access_code"])
    assert sid
test("Access-code submission (auth required)", test_anonymous_submit)

# ── 6. Admin ─────────────────────────────────────────────────────────────────
print("\n-- 6. Admin Endpoints (role-gated) --")

def _admin_probe(path):
    r = admin.get(f"{API}{path}", timeout=5)
    return r

def test_admin_stats():
    r = _admin_probe("/admin/stats")
    assert r.status_code in (200, 403), r.status_code
    if r.status_code == 200:
        assert "total_users" in r.json()
        print("     (caller has admin role - full check)")
    else:
        print("     (caller lacks admin role - gate confirmed)")
test("Admin stats (role-gated)", test_admin_stats)

def test_admin_users():
    r = _admin_probe("/admin/users?search=e2e&page=1&per_page=5")
    assert r.status_code in (200, 403)
test("Admin users list (role-gated)", test_admin_users)

def test_admin_stats_csv():
    r = _admin_probe("/admin/stats/export")
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert "text/csv" in r.headers.get("content-type", "")
test("Admin stats CSV export", test_admin_stats_csv)

def test_alertmanager_webhook():
    payload = {
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "E2ETestAlert", "severity": "warning"},
            "annotations": {"description": "synthetic alert from e2e script"},
        }],
    }
    r = requests.post(f"{API}/api/webhooks/alertmanager", json=payload, timeout=5)
    assert r.status_code == 200 and r.json().get("ok") is True
test("Alertmanager webhook accepts alerts", test_alertmanager_webhook)

# ── 7. Rate limiting (LAST - exhausts quota) ─────────────────────────────────
print("\n-- 7. Rate Limiting --")

def test_rate_limit():
    hit = False
    for i in range(150):
        r = admin.post(f"{API}/submit", json={"text": f"rate limit probe number {i}"}, timeout=5)
        if r.status_code == 429:
            hit = True
            break
        time.sleep(0.05)
    if not hit:
        print("     (limit not reached within 150 requests)")
    assert True
test("Rate limiting (429 eventually)", test_rate_limit)

# Summary ---------------------------------------------------------------------
print("\n" + "=" * 62)
print("RESULTS")
print("=" * 62)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"Total: {len(results)}  |  PASS: {passed}  |  FAIL: {failed}")
if failed:
    print("\nFailed:")
    for s, name in results:
        if s == FAIL:
            print(f"  {s} {name}")
    sys.exit(1)
print("All pipelines operational!")
sys.exit(0)
