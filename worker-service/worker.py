"""
Worker service - processes plagiarism detection jobs from queue.
"""
import sys
import os
import time
import json
from pathlib import Path
import requests
from pypdf import PdfReader
from docx import Document

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.models import Job, JobStatus
from shared.queue_client import QueueClient
from shared.plagiarism import PlagiarismDetector, compare_with_database
from shared.database import init_db, store_job_result, update_job_status, get_submissions_by_batch, store_similarity_results
from shared.vectorizer import TextVectorizer
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Get worker ID from environment
WORKER_ID = os.getenv('WORKER_ID', 'worker-default')
STORAGE_DIR = Path('/app/storage')
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Prometheus metrics
JOBS_PROCESSED = Counter('plagioscale_worker_jobs_processed_total', 'Total jobs processed by worker')
JOBS_FAILED = Counter('plagioscale_worker_jobs_failed_total', 'Total jobs failed')
JOB_DURATION = Histogram('plagioscale_worker_job_duration_seconds', 'Job processing time')
WORKER_QUEUE_LENGTH = Gauge('plagioscale_worker_queue_length', 'Queue length seen by worker')

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
        self.detector = PlagiarismDetector(k=5)
        print(f"[{WORKER_ID}] Worker initialized")
    
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
            # detect special batch-compute jobs
            try:
                payload = json.loads(job.text)
                if isinstance(payload, dict) and payload.get('type') == 'BATCH_COMPUTE':
                    batch_id = payload.get('batch_id')
                    return self.process_batch_compute(job, batch_id)
            except Exception:
                # not a batch job, continue with normal processing
                pass
            job_start_time = time.time()
            
            # Update status to PROCESSING
            self.queue_client.update_job_status(job.job_id, JobStatus.PROCESSING)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.PROCESSING.value, worker_id=WORKER_ID)
            
            # Simulate processing time (can be reduced for testing)
            time.sleep(1)
            
            # Run plagiarism detection against database
            comparison_results = compare_with_database(job.text, self.detector)
            
            # Calculate overall plagiarism score
            scores = [r['plagiarism_score'] for r in comparison_results]
            max_score = max(scores) if scores else 0.0
            avg_score = sum(scores) / len(scores) if scores else 0.0
            
            result = {
                'max_plagiarism_score': round(max_score, 4),
                'avg_plagiarism_score': round(avg_score, 4),
                'comparison_results': comparison_results,
                'text_length': len(job.text),
                'algorithm': 'k-shingle + cosine similarity'
            }
            
            # Store result in Redis
            self.queue_client.store_result(job.job_id, result)
            if self.db_ready:
                store_job_result(job.job_id, result, worker_id=WORKER_ID)
            
            # Save result to file as well (for durability)
            self._save_to_file(job.job_id, result)
            
            # Record metrics
            job_duration = time.time() - job_start_time
            JOB_DURATION.observe(job_duration)
            JOBS_PROCESSED.inc()
            print(f"[{WORKER_ID}] ✓ Job {job.job_id} completed (score: {max_score:.4f})")
            return True
            
        except Exception as e:
            print(f"[{WORKER_ID}] ✗ Error processing job {job.job_id}: {e}")
            self.queue_client.update_job_status(job.job_id, JobStatus.FAILED)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.FAILED.value, worker_id=WORKER_ID, error=str(e))
            JOBS_FAILED.inc()
            return False


    def process_batch_compute(self, job: Job, batch_id: str) -> bool:
        """Process a batch compute job: vectorize all submissions and store similarity matrix."""
        try:
            print(f"[{WORKER_ID}] Starting batch compute for {batch_id} (job {job.job_id})")
            job_start = time.time()

            # Update status
            self.queue_client.update_job_status(job.job_id, JobStatus.PROCESSING)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.PROCESSING.value, worker_id=WORKER_ID)

            # Fetch submissions
            submissions = get_submissions_by_batch(batch_id) if self.db_ready else []
            if not submissions:
                raise RuntimeError('No submissions found for batch')

            vec = TextVectorizer()
            api_host = os.getenv('API_HOST', 'api-service')
            api_port = os.getenv('API_PORT', '8000')
            notify_url = f'http://{api_host}:{api_port}/portal/notify'
            processed = 0
            total = len(submissions)
            for sub in submissions:
                try:
                    text = self._extract_text(sub['file_path'])
                    if not vec.add_document(sub['submission_id'], text):
                        print(f"[{WORKER_ID}] Warning: extracted text too short for {sub.get('file_path')}")
                except Exception as e:
                    print(f"[{WORKER_ID}] Warning: failed reading {sub.get('file_path')}: {e}")
                processed += 1
                # notify API of progress (best-effort)
                try:
                    requests.post(notify_url, json={'batch_id': batch_id, 'processed': processed, 'total': total}, timeout=2)
                except Exception:
                    pass

            matrix = vec.compute_similarity_matrix()
            if matrix:
                store_similarity_results(batch_id, matrix)

            result = {
                'batch_id': batch_id,
                'num_submissions': len(submissions),
                'algorithm': 'TF-IDF cosine (with file text extraction)',
            }
            # store job result
            self.queue_client.store_result(job.job_id, result)
            if self.db_ready:
                store_job_result(job.job_id, result, worker_id=WORKER_ID)

            # Save to file
            self._save_to_file(job.job_id, result)

            # metrics
            JOBS_PROCESSED.inc()
            JOB_DURATION.observe(time.time() - job_start)
            print(f"[{WORKER_ID}] ✓ Batch compute completed for {batch_id} (job {job.job_id})")
            return True
        except Exception as e:
            print(f"[{WORKER_ID}] ✗ Batch compute failed for {batch_id}: {e}")
            self.queue_client.update_job_status(job.job_id, JobStatus.FAILED)
            if self.db_ready:
                update_job_status(job.job_id, JobStatus.FAILED.value, worker_id=WORKER_ID, error=str(e))
            JOBS_FAILED.inc()
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
            reader = PdfReader(file_path)
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or '')
            return '\n'.join(parts)

        if suffix == '.docx':
            doc = Document(file_path)
            return '\n'.join(p.text for p in doc.paragraphs)

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
    
    def run(self):
        """Main worker loop - continuously pull and process jobs."""
        print(f"[{WORKER_ID}] Starting worker loop...")
        
        while True:
            try:
                # Block until job available (5 sec timeout)
                job = self.queue_client.dequeue_job(timeout=5)
                
                if job:
                    self.process_job(job)
                else:
                    # Queue empty, idle
                    queue_len = self.queue_client.get_queue_length()
                    try:
                        WORKER_QUEUE_LENGTH.set(queue_len)
                    except Exception:
                        pass
                    if queue_len == 0:
                        print(f"[{WORKER_ID}] Idle (queue empty)")
                    
            except KeyboardInterrupt:
                print(f"[{WORKER_ID}] Shutting down...")
                break
            except Exception as e:
                print(f"[{WORKER_ID}] Error in worker loop: {e}")
                time.sleep(1)


if __name__ == "__main__":
    worker = Worker()
    worker.run()
