"""Integration tests for API routes using FastAPI TestClient."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Save original env vars to avoid polluting other test files
_saved_env = {k: os.environ.get(k) for k in ("DB_HOST", "REDIS_HOST", "REDIS_PASSWORD")}
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PASSWORD", "plagio_redis_pass")

import main  # noqa: E402, F401

client = TestClient(main.app)


@pytest.mark.integration
def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("healthy", "degraded")


@pytest.mark.integration
def test_metrics_endpoint():
    resp = client.get("/metrics")
    assert resp.status_code == 200


@pytest.mark.integration
@patch("main.queue_client.enqueue_job", new_callable=AsyncMock)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_submit_text_empty(mock_connect, mock_enqueue):
    resp = client.post("/submit", json={"text": ""})
    assert resp.status_code == 400


@pytest.mark.integration
@patch("main.queue_client.enqueue_job", new_callable=AsyncMock)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_submit_text_short(mock_connect, mock_enqueue):
    resp = client.post("/submit", json={"text": "short"})
    assert resp.status_code == 400


@pytest.mark.integration
@patch("main.queue_client.enqueue_job", new_callable=AsyncMock, return_value=True)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_submit_text_success(mock_connect, mock_enqueue):
    resp = client.post("/submit", json={"text": "This is a long enough text for submission testing purposes"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert "job_id" in data


@pytest.mark.integration
@patch("main.queue_client.enqueue_job", new_callable=AsyncMock, return_value=False)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_submit_text_queue_failure(mock_connect, mock_enqueue):
    resp = client.post("/submit", json={"text": "This is a long enough text for submission testing purposes"})
    assert resp.status_code == 500


@pytest.mark.integration
@patch("main.queue_client.get_queue_length", new_callable=AsyncMock, return_value=5)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_queue_stats(mock_connect, mock_getlen):
    resp = client.get("/queue/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queue_length"] == 5


@pytest.mark.integration
@patch("main.queue_client.get_job_status", new_callable=AsyncMock, return_value="PENDING")
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_get_status(mock_connect, mock_getstatus):
    resp = client.get("/status/test-job-id")
    assert resp.status_code in (200, 404)


@pytest.mark.integration
def test_auth_signup_no_db():
    resp = client.post(
        "/auth/signup",
        json={"email": "test@example.com", "password": "pass123"},
    )
    assert resp.status_code == 500


@pytest.mark.integration
def test_auth_login_no_db():
    resp = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "pass123"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
@patch("main.queue_client.get_job_status", new_callable=AsyncMock, return_value=None)
@patch("main.queue_client.get_result", new_callable=AsyncMock, return_value=None)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_result_not_found(mock_connect, mock_getresult, mock_getstatus):
    resp = client.get("/result/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.integration
@patch("main.queue_client.get_queue_length", new_callable=AsyncMock, return_value=0)
@patch("main.queue_client.connect", new_callable=AsyncMock)
async def test_queue_stats_empty(mock_connect, mock_getlen):
    resp = client.get("/queue/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["queue_length"] == 0
