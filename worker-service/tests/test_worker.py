"""Integration tests for the worker service."""

import json
from unittest.mock import patch

import pytest

from shared.models import Job


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
def test_worker_init(mock_qc, mock_init_db):
    import worker
    w = worker.Worker()
    assert w.db_ready is False
    assert w.ai_detector is not None


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
def test_process_job_deprecated_individual(mock_qc_init, mock_init_db):
    import worker
    w = worker.Worker()
    job = Job(job_id="test-job-001", text="plain text non-JSON job")
    result = w.process_job(job)
    assert result is True
    w.queue_client.store_result.assert_called_once_with("test-job-001", {"skipped": True})


@pytest.mark.integration
@patch("worker.init_db", return_value=False)
@patch("worker.QueueClient")
def test_process_job_failure(mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    # make store_result raise to trigger the outer except block
    w.queue_client.store_result.side_effect = RuntimeError("Simulated failure")
    w.queue_client.redis_client.hget.return_value = str(worker.MAX_RETRIES)
    job = Job(job_id="test-job-002", text="plain text that will trigger failure")
    result = w.process_job(job)
    assert result is False
    w.queue_client.update_job_status.assert_any_call("test-job-002", worker.JobStatus.FAILED)


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
@patch("worker.HybridSimilarityScorer")
@patch("worker.Worker._extract_text", return_value="This is a test document with sufficient text for similarity computation.")
@patch("worker.requests.post")
@patch("worker.store_similarity_results")
def test_process_batch_compute(mock_store_sim, mock_req_post, mock_extract, mock_scorer, mock_subs, mock_qc_init, mock_init_db):
    import worker

    mock_qc = mock_qc_init.return_value
    mock_qc.get_job_status.return_value = "PENDING"
    mock_qc.get_similarity_matrix.return_value = None

    mock_scorer_instance = mock_scorer.return_value
    mock_scorer_instance.add_document.side_effect = lambda doc_id, text: (
        mock_scorer_instance.doc_texts.__setitem__(doc_id, text) or
        mock_scorer_instance.doc_ids.append(doc_id) or True
    )
    mock_scorer_instance.doc_ids = []
    mock_scorer_instance.doc_texts = {}
    mock_scorer_instance.compute_similarity_matrix.return_value = {"matrix": [[0.0, 0.5], [0.5, 0.0]]}
    mock_scorer_instance.get_algorithm_label.return_value = "Hybrid (alpha=0.5) | SBERT: test | TF-IDF"

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
def test_process_job_completed_skips(mock_getrecord, mock_qc_init, mock_init_db):
    import worker

    w = worker.Worker()
    assert w.db_ready is True
    job = Job(job_id="test-job-004", text="plain text job")
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


@pytest.mark.integration
@patch("worker.init_db", return_value=True)
@patch("worker.QueueClient")
@patch("worker.get_submissions_by_batch", return_value=[
    {"submission_id": "sub-1", "file_path": "/tmp/nonexistent1.pdf"},
    {"submission_id": "sub-2", "file_path": "/tmp/nonexistent2.pdf"},
])
@patch("worker.HybridSimilarityScorer")
@patch("worker.requests.post")
@patch("worker.store_similarity_results")
def test_process_batch_compute_fails_on_extraction_error(mock_store_sim, mock_req_post, mock_scorer, mock_subs, mock_qc_init, mock_init_db):
    """Batch compute should FAIL when all documents fail text extraction."""
    import worker

    mock_qc = mock_qc_init.return_value
    mock_qc.get_job_status.return_value = "PENDING"

    mock_scorer_instance = mock_scorer.return_value
    mock_scorer_instance.doc_ids = []

    w = worker.Worker()
    batch_id = "batch-001"
    payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
    job = Job(job_id="test-batch-fail-001", text=payload)
    # Exhaust retries so it goes to FAILED
    w.queue_client.redis_client.hget.return_value = str(worker.MAX_RETRIES)
    result = w.process_job(job)
    assert result is False
    mock_qc.update_job_status.assert_any_call("test-batch-fail-001", worker.JobStatus.FAILED)
    mock_store_sim.assert_not_called()
