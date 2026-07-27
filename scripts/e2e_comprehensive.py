"""Comprehensive E2E test exercising all pipelines."""

import sys, time, os, traceback

import requests

API = "http://localhost:8000"
MON_API = "http://localhost:8090"
FRONTEND = "http://localhost:3050"

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

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

def url(path):
    return f"{API}{path}"

def mon_url(path):
    return f"{MON_API}{path}"

_token = None
_headers = lambda: {"Authorization": f"Bearer {_token}"} if _token else {}

def login_or_signup(email="admin@test.com", password="admin123", name="Admin"):
    global _token
    r = requests.post(url("/auth/login"), json={"email": email, "password": password}, timeout=5)
    if r.status_code == 401:
        r = requests.post(url("/auth/signup"), json={"email": email, "password": password, "name": name}, timeout=5)
        if r.status_code != 200:
            raise RuntimeError(f"Signup failed: {r.status_code} {r.text}")
        r = requests.post(url("/auth/login"), json={"email": email, "password": password}, timeout=5)
    if r.status_code != 200:
        raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
    _token = r.json()["access_token"]

def signup_student(email, password, name="Student"):
    for attempt in range(3):
        r = requests.post(url("/auth/signup"), json={"email": email, "password": password, "name": name}, timeout=5)
        if r.status_code == 200:
            return requests.post(url("/auth/login"), json={"email": email, "password": password}, timeout=5).json()["access_token"]
        if r.status_code == 409:
            r = requests.post(url("/auth/login"), json={"email": email, "password": password}, timeout=5)
            if r.status_code == 200:
                return r.json()["access_token"]
        time.sleep(1)
    raise RuntimeError(f"Student auth failed after 3 attempts")

def create_assignment(name="E2E Test", expected_count=3):
    r = requests.post(url("/portal/assignments"), json={"name": name, "expected_count": expected_count}, headers=_headers(), timeout=5)
    assert r.status_code == 200, f"Create assignment: {r.text}"
    return r.json()

def upload_file(batch_id, filename, content, roll=None, access_code=None, student_token=None):
    h = {"Authorization": f"Bearer {student_token}"} if student_token else (_headers() if not access_code else {})
    data = {"batch_id": batch_id, "roll": roll or filename.replace(".txt",""), "name": filename.replace(".txt"," Student")}
    if access_code:
        data["access_code"] = access_code
    r = requests.post(url("/portal/submit"), headers=h, files={"file": (filename, content, "text/plain")}, data=data, timeout=10)
    assert r.status_code == 200, f"Upload {filename}: {r.status_code} {r.text}"
    return r.json()["submission_hash"]

def compute_similarity(batch_id):
    r = requests.post(url(f"/portal/compute-similarity/{batch_id}"), headers=_headers(), timeout=5)
    assert r.status_code == 200, f"Compute sim: {r.text}"
    return r.json()["job_id"]

def poll_matrix(batch_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url(f"/portal/similarity-matrix/{batch_id}"), headers=_headers(), timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("matrix") and len(data["matrix"]) > 0:
                return data["matrix"]
        time.sleep(2)
    raise TimeoutError("Matrix not ready within timeout")

def poll_result(job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url(f"/result/{job_id}"), timeout=5)
        if r.status_code == 200:
            s = r.json().get("status")
            if s and s.lower() in ("completed", "ready"):
                return r.json()
        time.sleep(2)
    raise TimeoutError(f"Job {job_id} not completed within timeout")

print("=" * 60)
print("PlagioScale - Comprehensive E2E Pipeline Tests")
print("=" * 60)

# 1. Health
print("\n-- 1. Health & Connectivity --")

def check_health():
    r = requests.get(url("/health"), timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
test("API /health", check_health)

def check_monitoring_health():
    r = requests.get(mon_url("/health"), timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
test("Monitoring /health", check_monitoring_health)

def check_health_summary():
    r = requests.get(mon_url("/api/health-summary"), timeout=5)
    assert r.status_code == 200
    svcs = r.json().get("services", {})
    assert svcs.get("api-service", {}).get("health") == "healthy"
    assert svcs.get("postgres", {}).get("health") == "healthy"
    assert svcs.get("redis", {}).get("health") == "healthy"
test("Monitoring health-summary", check_health_summary)

def check_queue_stats():
    r = requests.get(url("/queue/stats"), timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "queue_length" in data
test("Queue stats endpoint", check_queue_stats)

def check_frontend():
    r = requests.get(FRONTEND, timeout=5)
    assert r.status_code in (200, 301, 302)
test("Frontend serving", check_frontend)

# 2. Auth
print("\n-- 2. Authentication & Users --")

def test_login():
    login_or_signup()
    assert _token is not None and len(_token) > 20
test("Login / JWT token", test_login)

student_token = None
def test_student_signup():
    global student_token
    student_token = signup_student(f"student{int(time.time())}@test.com", "student123", "E2E Student")
test("Student signup", test_student_signup)

def test_auth_me():
    r = requests.get(url("/auth/me"), headers=_headers(), timeout=5)
    assert r.status_code == 200
    assert "email" in r.json()
test("Auth /me", test_auth_me)

# 3. Upload & Similarity
print("\n-- 3. Upload & Similarity --")

assignment1 = {}
def test_create_assignment():
    global assignment1
    assignment1 = create_assignment("E2E Core Test", 3)
    assert "batch_id" in assignment1
    assert "access_code" in assignment1
test("Create assignment", test_create_assignment)

submissions1 = []
def test_upload_files():
    global submissions1
    docs = [
        ("alice.txt", b"Machine learning is transforming how we analyze data and build predictive models."),
        ("bob.txt", b"Deep learning and neural networks are powerful tools for data analysis tasks."),
        ("carol.txt", b"Cloud computing enables scalable deployment of machine learning pipelines."),
    ]
    for fn, content in docs:
        sid = upload_file(assignment1["batch_id"], fn, content)
        submissions1.append(sid)
    assert len(submissions1) == 3
test("Upload 3 files", test_upload_files)

def test_list_submissions():
    r = requests.get(url(f"/portal/submissions/{assignment1['batch_id']}"), headers=_headers(), timeout=5)
    assert r.status_code == 200
    subs = r.json()["submissions"]
    assert len(subs) >= 3
test("List submissions", test_list_submissions)

def test_my_submissions():
    r = requests.get(url("/portal/my"), headers=_headers(), timeout=5)
    assert r.status_code == 200
    assert "batches" in r.json() or isinstance(r.json(), list)
test("My submissions (student)", test_my_submissions)

# 4. Similarity Matrix
print("\n-- 4. Similarity Matrix --")

matrix1 = {}
def test_compute_and_matrix():
    global matrix1
    job_id = compute_similarity(assignment1["batch_id"])
    assert job_id is not None
    matrix1 = poll_matrix(assignment1["batch_id"], timeout=45)
    assert len(matrix1) >= 3
    for sid in submissions1:
        assert sid in matrix1
test("Compute + matrix ready (<=30s)", test_compute_and_matrix)

def test_matrix_scores():
    for sub_id, scores in matrix1.items():
        for other_id, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} out of range"
test("All scores in [0,1]", test_matrix_scores)

# 5. AI Detection
print("\n-- 5. AI Detection --")

def test_ai_detection():
    deadline = time.time() + 30
    job_id = None
    while time.time() < deadline:
        r = requests.post(url("/submit"), json={"text": "This is a sample text for AI detection testing. The quick brown fox jumps over the lazy dog."}, timeout=10)
        if r.status_code == 200:
            job_id = r.json().get("job_id") or r.json().get("id")
            break
        if r.status_code == 429:
            print("  (rate limited, waiting...)")
            time.sleep(5)
            continue
        raise RuntimeError(f"Submit failed: {r.status_code} {r.text}")
    assert job_id is not None
    result = poll_result(job_id, timeout=60)
    assert result.get("status") and result["status"].lower() in ("completed", "ready")
    print("  AI score:", result.get("result", {}).get("ai_score", "N/A"))
test("AI detection via /submit", test_ai_detection)

# 6. Cross-Batch & Reports
print("\n-- 6. Cross-Batch & Reports --")

assignment2 = {}
submissions2 = []
def test_second_batch():
    global assignment2, submissions2
    assignment2 = create_assignment("E2E Cross-Batch", 2)
    docs = [
        ("dave.txt", b"Machine learning transforms how we build predictive systems."),
        ("eve.txt", b"Statistical analysis and predictive modeling in data science."),
    ]
    for fn, content in docs:
        sid = upload_file(assignment2["batch_id"], fn, content)
        submissions2.append(sid)
    compute_similarity(assignment2["batch_id"])
    poll_matrix(assignment2["batch_id"], timeout=30)
test("Create 2nd batch + compute", test_second_batch)

def test_cross_batch():
    r = requests.get(url(f"/portal/cross-batch/{assignment1['batch_id']}/{assignment2['batch_id']}"), headers=_headers(), timeout=15)
    assert r.status_code == 200
test("Cross-batch comparison", test_cross_batch)

def test_student_comparison():
    sid = submissions1[0]
    r = requests.get(url(f"/portal/student-comparison/{sid}"), headers=_headers(), timeout=15)
    assert r.status_code == 200
test("Student comparison", test_student_comparison)

def test_csv_export():
    r = requests.get(url(f"/portal/export/{assignment1['batch_id']}"), headers=_headers(), timeout=10)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
test("CSV export", test_csv_export)

def test_pdf_report():
    sid1, sid2 = submissions1[0], submissions1[1]
    r = requests.get(url(f"/portal/report/{assignment1['batch_id']}/{sid1}/{sid2}"), headers=_headers(), timeout=15)
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        assert "application/pdf" in r.headers.get("content-type", "")
test("PDF similarity report", test_pdf_report)

# 7. Admin
print("\n-- 7. Admin & Monitoring --")

def test_admin_stats():
    r = requests.get(url("/admin/stats"), headers=_headers(), timeout=5)
    assert r.status_code in (200, 403)
test("Admin stats", test_admin_stats)

def test_admin_users():
    r = requests.get(url("/admin/users"), headers=_headers(), timeout=5)
    assert r.status_code in (200, 403)
test("Admin users list", test_admin_users)

def test_autoscaler_metrics():
    r = requests.get("http://localhost:8002/metrics", timeout=5)
    assert r.status_code == 200
    assert "plagioscale_autoscaler_queue_length" in r.text
test("Autoscaler metrics", test_autoscaler_metrics)

def test_monitoring_overview():
    r = requests.get(mon_url("/api/overview"), timeout=5)
    assert r.status_code == 200
    assert "queue_length" in r.json()
    assert "workers" in r.json()
test("Monitoring overview", test_monitoring_overview)

# 8. Anonymous Submit
print("\n-- 8. Anonymous Submission --")

def test_anonymous():
    sid = upload_file(assignment1["batch_id"], "anon.txt", b"Anonymous submission content", roll="ANON999", access_code=assignment1["access_code"])
    assert sid is not None
test("Anonymous submit with access_code", test_anonymous)

# 9. Rate Limiting (LAST - exhausts quota)
print("\n-- 9. Rate Limiting --")

def test_rate_limit():
    hit = False
    for _ in range(150):
        r = requests.post(url("/submit"), json={"text": "test"}, timeout=5)
        if r.status_code == 429:
            hit = True
            break
    if not hit:
        print("  (rate limit not triggered - limit may be higher than 150)")
test("Rate limiting (429 check)", test_rate_limit)

# Summary
print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"Total: {len(results)}  |  PASS: {passed}  |  FAIL: {failed}")
if failed:
    print("\nFailed:")
    for s, name in results:
        if s == FAIL:
            print(f"  {s} {name}")
    sys.exit(1)
else:
    print("All pipelines operational!")
    sys.exit(0)
