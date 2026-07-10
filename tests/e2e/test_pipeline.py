"""Full-stack E2E test: create assignment → upload → compute → verify matrix.

Requires the full Docker Compose stack to be running (api + db + redis + worker).
Marked @pytest.mark.e2e so it is skipped in CI by default.
"""

import time

import pytest
import requests

API_BASE = "http://localhost:8000"


def _url(path: str) -> str:
    return f"{API_BASE}{path}"


@pytest.fixture(scope="module")
def jwt_token():
    """Obtain a teacher JWT via login (uses seed user if available)."""
    resp = requests.post(
        _url("/auth/login"),
        json={"email": "admin@plagioscale.local", "password": "admin123"},
        timeout=5,
    )
    if resp.status_code == 401:
        # try seeding with signup first
        resp = requests.post(
            _url("/auth/signup"),
            json={"email": "admin@plagioscale.local", "password": "admin123", "name": "Admin"},
            timeout=5,
        )
        if resp.status_code != 200:
            pytest.skip("Cannot authenticate — is the stack running?")
        resp = requests.post(
            _url("/auth/login"),
            json={"email": "admin@plagioscale.local", "password": "admin123"},
            timeout=5,
        )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


@pytest.mark.e2e
def test_health():
    resp = requests.get(_url("/health"), timeout=5)
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@pytest.mark.e2e
def test_full_pipeline(auth_headers):
    # ------------------------------------------------------------------ #
    # 1. Create an assignment
    # ------------------------------------------------------------------ #
    resp = requests.post(
        _url("/portal/assignments"),
        json={"name": "E2E Test Assignment", "expected_count": 3},
        headers=auth_headers,
        timeout=5,
    )
    assert resp.status_code == 200, f"Create assignment failed: {resp.text}"
    data = resp.json()
    batch_id = data["batch_id"]
    access_code = data["access_code"]
    assert batch_id, "No batch_id returned"
    assert access_code, "No access_code returned"

    # ------------------------------------------------------------------ #
    # 2. Upload 3 files via authenticated route
    # ------------------------------------------------------------------ #
    docs = [
        ("doc1.txt", b"Machine learning is transforming how we analyze data and build predictive models."),
        ("doc2.txt", b"Deep learning and neural networks are powerful tools for data analysis tasks."),
        ("doc3.txt", b"Cloud computing enables scalable deployment of machine learning pipelines."),
    ]
    submission_ids = []
    for filename, content in docs:
        resp = requests.post(
            _url("/portal/submit"),
            headers=auth_headers,
            files={"file": (filename, content, "text/plain")},
            data={"batch_id": batch_id, "roll": filename.replace(".txt", ""), "name": filename.replace(".txt", " Student")},
            timeout=10,
        )
        assert resp.status_code == 200, f"Upload {filename} failed: {resp.text}"
        sid = resp.json()["submission_hash"]
        submission_ids.append(sid)
    assert len(submission_ids) == 3

    # ------------------------------------------------------------------ #
    # 3. Verify submissions are visible
    # ------------------------------------------------------------------ #
    resp = requests.get(
        _url(f"/portal/submissions/{batch_id}"),
        headers=auth_headers,
        timeout=5,
    )
    assert resp.status_code == 200
    subs = resp.json()["submissions"]
    assert len(subs) >= 3, f"Expected >=3 submissions, got {len(subs)}"

    # ------------------------------------------------------------------ #
    # 4. Trigger batch similarity computation
    # ------------------------------------------------------------------ #
    resp = requests.post(
        _url(f"/portal/compute-similarity/{batch_id}"),
        headers=auth_headers,
        timeout=5,
    )
    assert resp.status_code == 200, f"Compute similarity failed: {resp.text}"
    job_id = resp.json()["job_id"]

    # ------------------------------------------------------------------ #
    # 5. Poll for similarity results (worker may take a few seconds)
    # ------------------------------------------------------------------ #
    matrix = None
    deadline = time.time() + 30
    while time.time() < deadline:
        resp = requests.get(
            _url(f"/portal/similarity-matrix/{batch_id}"),
            headers=auth_headers,
            timeout=5,
        )
        if resp.status_code == 200:
            matrix = resp.json()["matrix"]
            break
        time.sleep(2)

    assert matrix is not None, "Similarity matrix was not computed within 30s"
    assert len(matrix) >= 3, f"Expected >=3 entries in matrix, got {len(matrix)}"

    # verify all submission IDs appear in the matrix keys
    for sid in submission_ids:
        assert sid in matrix, f"Submission {sid} missing from matrix"

    # verify scores are in [0, 1]
    for sub_id, scores in matrix.items():
        for other_id, score in scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {sub_id}/{other_id}"


@pytest.mark.e2e
def test_anonymous_submission_flow():
    """Test the anonymous student flow: signup → submit via access_code."""
    # create assignment via admin
    resp = requests.post(
        _url("/auth/login"),
        json={"email": "admin@plagioscale.local", "password": "admin123"},
        timeout=5,
    )
    if resp.status_code != 200:
        pytest.skip("Stack not running or admin user missing")
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.post(
        _url("/portal/assignments"),
        json={"name": "Anonymous E2E", "expected_count": 2},
        headers=headers,
        timeout=5,
    )
    assert resp.status_code == 200
    access_code = resp.json()["access_code"]

    # anonymous student submits via access_code (no JWT header)
    resp = requests.post(
        _url("/portal/submit"),
        files={"file": ("anon.txt", b"Anonymous student submission content here.", "text/plain")},
        data={"access_code": access_code, "roll": "ANON001", "name": "Anon Student"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Anonymous submit failed: {resp.text}"
    assert "submission_hash" in resp.json()
