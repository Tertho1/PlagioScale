"""Integration tests for the worker service."""

from unittest.mock import MagicMock, patch

import pytest

from shared.models import Job, JobStatus
from shared.plagiarism import compare_with_database


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
def test_worker_init(mock_qc, mock_init_db):
    import worker
    w = worker.Worker()
    assert w.db_ready is False
    assert w.detector is not None


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
@patch("worker.compare_with_database", return_value=[
    {"source_id": "doc1", "plagiarism_score": 0.75}
])
def test_process_job_success(mock_compare, mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    job = Job(job_id="test-job-001", text="This is a test document for plagiarism checking purposes.")
    result = w.process_job(job)
    assert result is True
    w.queue_client.store_result.assert_called_once()
    w.queue_client.update_job_status.assert_any_call("test-job-001", JobStatus.PROCESSING)
    args, _ = w.queue_client.store_result.call_args
    assert args[0] == "test-job-001"
    assert "max_plagiarism_score" in args[1]


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
@patch("worker.compare_with_database", side_effect=Exception("Simulated failure"))
def test_process_job_failure(mock_compare, mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    job = Job(job_id="test-job-002", text="This is a test document that will fail.")
    result = w.process_job(job)
    assert result is False
    w.queue_client.update_job_status.assert_any_call("test-job-002", JobStatus.FAILED)


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
def test_process_job_short_text(mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    job = Job(job_id="test-job-003", text="short")
    result = w.process_job(job)
    assert result is True


@pytest.mark.integration
@patch("worker.init_db", return_value=True)
@patch("worker.QueueClient")
@patch("worker.get_submissions_by_batch", return_value=[
    {"submission_id": "sub-1", "file_path": "/tmp/fake1.pdf"},
    {"submission_id": "sub-2", "file_path": "/tmp/fake2.pdf"},
])
@patch("worker.TextVectorizer")
@patch("worker.requests.post")
@patch("worker.store_similarity_results")
def test_process_batch_compute(mock_store_sim, mock_req_post, mock_vec, mock_subs, mock_qc_init, mock_init_db):
    import json
    import worker

    mock_qc = mock_qc_init.return_value
    mock_qc.get_job_status.return_value = "PENDING"
    mock_qc.get_similarity_matrix.return_value = None

    mock_vec_instance = mock_vec.return_value
    mock_vec_instance.compute_similarity_matrix.return_value = {"matrix": [[0.0, 0.5], [0.5, 0.0]]}

    w = worker.Worker()
    batch_id = "batch-001"
    payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
    job = Job(job_id="test-batch-001", text=payload)
    result = w.process_job(job)
    assert result is True
    mock_store_sim.assert_called_once()


@pytest.mark.integration
@patch("worker.init_db", return_value=True)
@patch("worker.QueueClient")
@patch("worker.get_job_record", return_value={"status": "COMPLETED"})
@patch("worker.update_job_status")
@patch("worker.store_job_result")
@patch("worker.compare_with_database", return_value=[
    {"source_id": "doc1", "plagiarism_score": 0.85}
])
def test_process_job_with_db(mock_compare, mock_store, mock_update, mock_getrecord, mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    assert w.db_ready is True
    job = Job(job_id="test-job-004", text="Document text for DB-backed processing.")
    result = w.process_job(job)
    assert result is True


@pytest.mark.integration
@patch("worker.init_db", return_value=True)
@patch("worker.QueueClient")
@patch("worker.get_job_record", return_value={"status": "CANCELLED"})
def test_process_cancelled_job(mock_getrecord, mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    job = Job(job_id="test-job-005", text="This job was cancelled.")
    result = w.process_job(job)
    assert result is True
