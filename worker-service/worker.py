"""
Worker service - processes plagiarism detection jobs from queue.
"""
import json
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from docx import Document
from pypdf import PdfReader

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from shared.ai_detector import AIContentDetector
from shared.database import (
    get_job_record,
    get_submissions_by_batch,
    init_db,
    store_job_result,
    store_similarity_results,
    update_job_status,
    update_submission_ai_score,
)
from shared.models import Job, JobStatus
from shared.queue_client import QueueClient
from shared.similarity_scorer import HybridSimilarityScorer

STALE_JOB_TIMEOUT = 300
MAX_RETRIES = 3
DEAD_LETTER_KEY = "dead_letter_jobs"
STALE_RETRY_KEY = "stale_job_retries"

# Get worker ID from environment
WORKER_ID = os.getenv('WORKER_ID') or socket.gethostname()
WORKER_SECRET = os.getenv('WORKER_SECRET', '')
STORAGE_DIR = Path('/app/storage')
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Prometheus metrics (all labelled with worker_id)
JOBS_PROCESSED = Counter('plagioscale_worker_jobs_processed_total', 'Total jobs processed by worker', labelnames=['worker_id'])
JOBS_FAILED = Counter('plagioscale_worker_jobs_failed_total', 'Total jobs failed', labelnames=['worker_id'])
JOB_DURATION = Histogram('plagioscale_worker_job_duration_seconds', 'Job processing time', labelnames=['worker_id'])
WORKER_QUEUE_LENGTH = Gauge('plagioscale_worker_queue_length', 'Queue length seen by worker', labelnames=['worker_id'])

# Start metrics HTTP server for Prometheus
try:
    start_http_server(8001)
    print(f"[{WORKER_ID}] Prometheus metrics available on port 8001")
except Exception:
    print(f"[{WORKER_ID}] Warning: Could not start Prometheus HTTP server")


class Worker:
    """Worker process that pulls and processes jobs."""

    def __init__(self):
        """Initialize worker."""
        self.queue_client = QueueClient()
        self.db_ready = init_db()
        self.ai_detector = AIContentDetector()
        if self.ai_detector.available:
            print(f"[{WORKER_ID}] AI content detector loaded")
        else:
            print(f"[{WORKER_ID}] AI content detector not available (will skip AI scoring)")
        # Eagerly pre-load models so batch compute is fast
        self._warmup_models()
        print(f"[{WORKER_ID}] Worker initialized")

    def _warmup_models(self):
        """Pre-load heavyweight models at startup to avoid cold-start delay."""
        try:
            print(f"[{WORKER_ID}] Pre-loading DistilGPT2 for AI detection...")
            self.ai_detector._load_gpt2()
            print(f"[{WORKER_ID}] DistilGPT2 loaded")
        except Exception as e:
            print(f"[{WORKER_ID}] DistilGPT2 warmup skipped: {e}")
        try:
            print(f"[{WORKER_ID}] Pre-loading SBERT model for similarity...")
            from shared.vectorizer import _get_sbert
            _get_sbert("all-MiniLM-L12-v2")
            print(f"[{WORKER_ID}] SBERT model loaded")
        except Exception as e:
            print(f"[{WORKER_ID}] SBERT warmup skipped: {e}")

    def process_job(self, job: Job) -> bool:
        """
        Process a single job.

        Args:
            job: Job to process

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"[{WORKER_ID}] Processing job {job.job_id}")
            if self.db_ready:
                job_record = get_job_record(job.job_id)
                if job_record and job_record.get("status") == JobStatus.CANCELLED.value:
                    print(f"[{WORKER_ID}] Skipping cancelled job {job.job_id}")
                    return True
            try:
                payload = json.loads(job.text)
                if isinstance(payload, dict):
                    jt = payload.get('type')
                    batch_id = payload.get('batch_id')
                    if jt == 'AI_DETECTION':
                        return self.process_ai_detection(job, batch_id)
                    if jt in ('BATCH_COMPUTE', 'SIMILARITY_COMPUTE'):
                        return self.process_similarity(job, batch_id)
            except Exception:
                pass
            # Individual (single-submission) jobs are deprecated — skip them
            print(f"[{WORKER_ID}] Skipping deprecated individual job {job.job_id}")
            self.queue_client.store_result(job.job_id, {"skipped": True})
            JOBS_PROCESSED.labels(WORKER_ID).inc()
            return True

        except Exception as e:
            print(f"[{WORKER_ID}] ✗ Error processing job {job.job_id}: {e}")
            retries = int(self.queue_client.redis_client.hget(STALE_RETRY_KEY, job.job_id) or 0)
            if retries < MAX_RETRIES:
                print(f"[{WORKER_ID}] Re-enqueuing job {job.job_id} (retry {retries + 1}/{MAX_RETRIES})")
                self.queue_client.redis_client.hincrby(STALE_RETRY_KEY, job.job_id, 1)
                self.queue_client.enqueue_job(job)
            else:
                print(f"[{WORKER_ID}] Moving job {job.job_id} to dead letter (exhausted retries)")
                self.queue_client.redis_client.sadd(DEAD_LETTER_KEY, job.job_id)
                self.queue_client.redis_client.hset(f"dead_letter:{job.job_id}", "payload", job.to_json())
                self.queue_client.update_job_status(job.job_id, JobStatus.FAILED)
                if self.db_ready:
                    update_job_status(job.job_id, JobStatus.FAILED.value, worker_id=WORKER_ID, error=str(e))
            JOBS_FAILED.labels(WORKER_ID).inc()
            return False


    def _notify(self, batch_id: str, processed: int, total: int, done: bool = False):
        """Send progress notification to API service (fire-and-forget, never blocks the loop)."""
        api_host = os.getenv('API_HOST', 'api-service')
        api_port = os.getenv('API_PORT', '8000')
        use_mtls = os.getenv('USE_MTLS', '').lower() in ('true', '1')
        protocol = 'https' if use_mtls else 'http'
        notify_url = f'{protocol}://{api_host}:{api_port}/portal/notify'
        mtls_verify = '/app/certs/ca.crt' if use_mtls else None
        mtls_cert = ('/app/certs/worker.crt', '/app/certs/worker.key') if use_mtls else None

        def _post():
            try:
                headers = {}
                if WORKER_SECRET:
                    headers["X-Worker-Secret"] = WORKER_SECRET
                payload = {'batch_id': batch_id, 'processed': processed, 'total': total}
                if done:
                    payload['done'] = True
                requests.post(notify_url, json=payload, headers=headers, timeout=2, verify=mtls_verify, cert=mtls_cert)
            except Exception:
                pass

        threading.Thread(target=_post, daemon=True).start()

    def process_ai_detection(self, job: Job, batch_id: str) -> bool:
        """Process AI detection for all submissions in a batch."""
        try:
            print(f"[{WORKER_ID}] Starting AI detection for {batch_id} (job {job.job_id})")
            job_start = time.time()

            if self.db_ready:
                job_record = get_job_record(job.job_id)
                if job_record and job_record.get("status") == JobStatus.CANCELLED.value:
                    print(f"[{WORKER_ID}] Skipping cancelled AI job {job.job_id}")
                    return True

            self.queue_client.update_job_status(job.job_id, JobStatus.PROCESSING)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.PROCESSING.value, worker_id=WORKER_ID)

            submissions = get_submissions_by_batch(batch_id) if self.db_ready else []
            if not submissions:
                raise RuntimeError('No submissions found for batch')

            total = len(submissions)
            scored = 0
            for i, sub in enumerate(submissions):
                sub_id = sub.get('submission_id', '')
                # Skip already-scored submissions so retries don't redo work
                if self.db_ready and sub.get('ai_score') is not None:
                    scored += 1
                    self._notify(batch_id, i + 1, total)
                    continue
                try:
                    text = self._extract_text(sub['file_path'])
                    if self.ai_detector.available and text.strip():
                        ai_score = self._run_ai_detection(sub_id, text)
                        if ai_score >= 0 and self.db_ready:
                            update_submission_ai_score(sub_id, ai_score)
                            print(f"[{WORKER_ID}] AI score for {sub_id}: {ai_score:.4f}")
                except Exception as e:
                    print(f"[{WORKER_ID}] Warning: AI detection failed for {sub.get('file_path')}: {e}")
                self._notify(batch_id, i + 1, total)

            result = {'batch_id': batch_id, 'num_submissions': total, 'type': 'AI_DETECTION'}
            self.queue_client.store_result(job.job_id, result)
            if self.db_ready:
                store_job_result(job.job_id, result, worker_id=WORKER_ID)
            self._save_to_file(job.job_id, result)
            JOBS_PROCESSED.labels(WORKER_ID).inc()
            JOB_DURATION.labels(WORKER_ID).observe(time.time() - job_start)
            print(f"[{WORKER_ID}] ✓ AI detection completed for {batch_id} (job {job.job_id})")
            self.queue_client.update_job_status(job.job_id, JobStatus.COMPLETED)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.COMPLETED.value, worker_id=WORKER_ID)
            self._notify(batch_id, total, total, done=True)
            return True
        except Exception as e:
            print(f"[{WORKER_ID}] ✗ AI detection failed for {batch_id}: {e}")
            retries = int(self.queue_client.redis_client.hget(STALE_RETRY_KEY, job.job_id) or 0)
            if retries < MAX_RETRIES:
                self.queue_client.redis_client.hincrby(STALE_RETRY_KEY, job.job_id, 1)
                self.queue_client.enqueue_job(job)
            else:
                self.queue_client.redis_client.sadd(DEAD_LETTER_KEY, job.job_id)
                self.queue_client.redis_client.hset(f"dead_letter:{job.job_id}", "payload", job.to_json())
                self.queue_client.update_job_status(job.job_id, JobStatus.FAILED)
                if self.db_ready:
                    update_job_status(job.job_id, JobStatus.FAILED.value, worker_id=WORKER_ID, error=str(e))
            JOBS_FAILED.labels(WORKER_ID).inc()
            return False

    def process_similarity(self, job: Job, batch_id: str) -> bool:
        """Compute similarity matrix for all submissions in a batch."""
        try:
            time.sleep(0.5)  # Ensure queue depth is visible to autoscaler
            print(f"[{WORKER_ID}] Starting similarity compute for {batch_id} (job {job.job_id})")
            job_start = time.time()

            if self.db_ready:
                job_record = get_job_record(job.job_id)
                if job_record and job_record.get("status") == JobStatus.CANCELLED.value:
                    print(f"[{WORKER_ID}] Skipping cancelled similarity job {job.job_id}")
                    return True

            self.queue_client.update_job_status(job.job_id, JobStatus.PROCESSING)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.PROCESSING.value, worker_id=WORKER_ID)

            submissions = get_submissions_by_batch(batch_id) if self.db_ready else []
            if not submissions:
                raise RuntimeError('No submissions found for batch')

            vec = HybridSimilarityScorer(alpha=0.5)
            total = len(submissions)
            failed_files = []
            for i, sub in enumerate(submissions):
                sub_id = sub.get('submission_id', '')
                try:
                    text = self._extract_text(sub['file_path'])
                    if not vec.add_document(sub_id, text):
                        print(f"[{WORKER_ID}] Warning: extracted text too short for {sub.get('file_path')}")
                except Exception as e:
                    print(f"[{WORKER_ID}] Warning: failed reading {sub.get('file_path')}: {e}")
                    failed_files.append(sub.get('file_path', 'unknown'))
                self._notify(batch_id, i + 1, total)

            if len(vec.doc_ids) < 2:
                error_msg = f"Need at least 2 valid documents for similarity matrix (got {len(vec.doc_ids)})"
                if failed_files:
                    error_msg += f"; failed to read: {failed_files}"
                raise RuntimeError(error_msg)

            matrix = vec.compute_similarity_matrix()
            store_similarity_results(batch_id, matrix)

            result = {
                'batch_id': batch_id,
                'num_submissions': len(submissions),
                'documents_processed': len(vec.doc_ids),
                'failed_files': failed_files,
                'algorithm': vec.get_algorithm_label(),
                'type': 'SIMILARITY_COMPUTE',
            }
            self.queue_client.store_result(job.job_id, result)
            if self.db_ready:
                store_job_result(job.job_id, result, worker_id=WORKER_ID)
            self._save_to_file(job.job_id, result)
            JOBS_PROCESSED.labels(WORKER_ID).inc()
            JOB_DURATION.labels(WORKER_ID).observe(time.time() - job_start)
            print(f"[{WORKER_ID}] ✓ Similarity compute completed for {batch_id} (job {job.job_id})")
            self.queue_client.update_job_status(job.job_id, JobStatus.COMPLETED)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.COMPLETED.value, worker_id=WORKER_ID)
            self._notify(batch_id, total, total, done=True)
            return True
        except Exception as e:
            print(f"[{WORKER_ID}] ✗ Similarity compute failed for {batch_id}: {e}")
            retries = int(self.queue_client.redis_client.hget(STALE_RETRY_KEY, job.job_id) or 0)
            if retries < MAX_RETRIES:
                self.queue_client.redis_client.hincrby(STALE_RETRY_KEY, job.job_id, 1)
                self.queue_client.enqueue_job(job)
            else:
                print(f"[{WORKER_ID}] Moving batch job {job.job_id} to dead letter (exhausted retries)")
                self.queue_client.redis_client.sadd(DEAD_LETTER_KEY, job.job_id)
                self.queue_client.redis_client.hset(f"dead_letter:{job.job_id}", "payload", job.to_json())
                self.queue_client.update_job_status(job.job_id, JobStatus.FAILED)
                if self.db_ready:
                    update_job_status(job.job_id, JobStatus.FAILED.value, worker_id=WORKER_ID, error=str(e))
            JOBS_FAILED.labels(WORKER_ID).inc()
            return False

    def _extract_text(self, file_path: str) -> str:
        """Extract best-effort plain text from common assignment file formats."""
        suffix = Path(file_path).suffix.lower()

        if suffix in {'.txt', '.md', '.csv', '.py', '.java', '.js', '.ts'}:
            # Try multiple encodings to handle different text file formats
            for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='strict') as f:
                        return f.read()
                except (UnicodeDecodeError, LookupError):
                    continue
            # If all specific encodings fail, try with errors='ignore'
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        if suffix == '.pdf':
            with open(file_path, 'rb') as fh:
                reader = PdfReader(fh)
                parts = []
                for page in reader.pages:
                    parts.append(page.extract_text() or '')
                return '\n'.join(parts)

        if suffix == '.docx':
            doc = Document(file_path)
            text = '\n'.join(p.text for p in doc.paragraphs)
            return text

        # fallback for unknown formats - try multiple encodings
        for encoding in ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding, errors='strict') as f:
                    return f.read()
            except (UnicodeDecodeError, LookupError):
                continue
        # If all specific encodings fail, try with errors='ignore'
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _save_to_file(self, job_id: str, result: dict):
        """Save result to local storage."""
        try:
            result_file = STORAGE_DIR / f"{job_id}.json"
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            print(f"[{WORKER_ID}] Warning: Failed to save to file: {e}")

    def _run_ai_detection(self, sub_id: str, text: str) -> float:
        """Run AI detection on text and return ai_score. Suitable for thread pool."""
        try:
            return self.ai_detector.detect(text)
        except Exception as e:
            print(f"[{WORKER_ID}] AI detection failed for {sub_id}: {e}")
            return -1.0

    def _recover_stale_jobs(self):
        """Detect and recover zombie jobs stuck in PROCESSING state."""
        if not self.db_ready:
            return
        try:

            from shared.database import JobRecord, SessionLocal
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_JOB_TIMEOUT)
            session = SessionLocal()
            try:
                stale = session.query(JobRecord).filter(
                    JobRecord.status == JobStatus.PROCESSING.value,
                    JobRecord.updated_at < cutoff,
                ).all()
                if not stale:
                    return
                print(f"[{WORKER_ID}] Found {len(stale)} stale job(s) to recover")
                for job in stale:
                    retries = int(self.queue_client.redis_client.hget(STALE_RETRY_KEY, job.job_id) or 0)
                    if retries >= MAX_RETRIES:
                        print(f"[{WORKER_ID}] Moving {job.job_id} to dead letter (retried {retries}x)")
                        self.queue_client.redis_client.sadd(DEAD_LETTER_KEY, job.job_id)
                        self.queue_client.redis_client.hset(f"dead_letter:{job.job_id}", "payload", job.to_json())
                        job.status = JobStatus.FAILED.value
                        job.error = f"Exceeded max retries ({MAX_RETRIES})"
                        job.completed_at = datetime.now(timezone.utc)
                        self.queue_client.redis_client.hdel(STALE_RETRY_KEY, job.job_id)
                    else:
                        print(f"[{WORKER_ID}] Re-enqueuing stale job {job.job_id} (retry {retries + 1}/{MAX_RETRIES})")
                        self.queue_client.redis_client.hincrby(STALE_RETRY_KEY, job.job_id, 1)
                        job.status = JobStatus.PENDING.value
                        job.error = None
                        job.worker_id = None
                        # Re-push to queue
                        from shared.models import Job as JobModel
                        recovery_job = JobModel(job_id=job.job_id, text=job.text)
                        self.queue_client.enqueue_job(recovery_job)
                    session.commit()
                # Also reconcile DB-FAILED jobs that are still PROCESSING in Redis
                failed_in_db = session.query(JobRecord).filter(
                    JobRecord.status == JobStatus.FAILED.value,
                    JobRecord.updated_at < cutoff,
                ).all()
                for job in failed_in_db:
                    redis_status = self.queue_client.redis_client.hget(f'job:{job.job_id}', 'status')
                    if redis_status == JobStatus.PROCESSING.value:
                        print(f"[{WORKER_ID}] Fixing Redis status for DB-FAILED job {job.job_id}")
                        self.queue_client.redis_client.hset(f'job:{job.job_id}', 'status', JobStatus.FAILED.value)
                        self.queue_client.redis_client.hdel(STALE_RETRY_KEY, job.job_id)
                        self.queue_client.redis_client.srem(DEAD_LETTER_KEY, job.job_id)
            finally:
                session.close()
        except Exception as e:
            print(f"[{WORKER_ID}] Error recovering stale jobs: {e}")

    def _drain_dead_letter(self):
        """Check dead letter queue and re-queue jobs that haven't exceeded max attempts."""
        try:
            dead_ids = self.queue_client.redis_client.smembers(DEAD_LETTER_KEY)
            if not dead_ids:
                return
            print(f"[{WORKER_ID}] Found {len(dead_ids)} job(s) in dead letter queue")
            for job_id in dead_ids:
                retries = int(self.queue_client.redis_client.hget(STALE_RETRY_KEY, job_id) or 0)
                if retries < MAX_RETRIES:
                    print(f"[{WORKER_ID}] Re-queuing dead letter job {job_id} (retry {retries + 1}/{MAX_RETRIES})")
                    self.queue_client.redis_client.srem(DEAD_LETTER_KEY, job_id)
                    self.queue_client.redis_client.hincrby(STALE_RETRY_KEY, job_id, 1)
                    stored_payload = self.queue_client.redis_client.hget(f"dead_letter:{job_id}", "payload")
                    if stored_payload:
                        from shared.models import Job as JobModel
                        recovery_job = JobModel.from_json(stored_payload)
                    else:
                        from shared.models import Job as JobModel
                        recovery_job = JobModel(job_id=job_id, text="")
                    self.queue_client.enqueue_job(recovery_job)
                else:
                    print(f"[{WORKER_ID}] Dead letter job {job_id} exceeded max retries — skipping")
        except Exception as e:
            print(f"[{WORKER_ID}] Error draining dead letter queue: {e}")

    def run(self):
        """Main worker loop - continuously pull and process jobs."""
        print(f"[{WORKER_ID}] Starting worker loop...")
        self._recover_stale_jobs()
        last_recovery = time.time()
        last_db_check = time.time()

        while True:
            try:
                now = time.time()
                if now - last_db_check >= 30:
                    try:
                        from sqlalchemy import text

                        from shared.database import SessionLocal
                        session = SessionLocal()
                        session.execute(text("SELECT 1"))
                        session.close()
                        if not self.db_ready:
                            self.db_ready = init_db()
                            if self.db_ready:
                                print(f"[{WORKER_ID}] Database reconnected")
                        elif self.db_ready:
                            pass
                    except Exception:
                        if self.db_ready:
                            self.db_ready = False
                            print(f"[{WORKER_ID}] Database connection lost — will retry")
                    last_db_check = now

                if now - last_recovery >= 60:
                    self._recover_stale_jobs()
                    self._drain_dead_letter()
                    last_recovery = now

                # Block until job available (5 sec timeout)
                job = self.queue_client.dequeue_job(timeout=5)

                if job:
                    self.process_job(job)
                else:
                    # Queue empty, idle
                    queue_len = self.queue_client.get_queue_length()
                    try:
                        WORKER_QUEUE_LENGTH.labels(WORKER_ID).set(queue_len)
                    except Exception:
                        pass
                    if queue_len == 0:
                        print(f"[{WORKER_ID}] Idle (queue empty)")

            except KeyboardInterrupt:
                print(f"[{WORKER_ID}] Shutting down...")
                break
            except Exception as e:
                print(f"[{WORKER_ID}] Error in worker loop: {e}")
                traceback.print_exc()
                time.sleep(1)


if __name__ == "__main__":
    worker = Worker()
    worker.run()
