"""
Stress testing script - simulates multiple plagiarism detection requests.
"""
import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


API_URL = "http://localhost:8000"

# Sample texts to test with
SAMPLE_TEXTS = [
    "Machine learning is a powerful tool for data analysis and prediction.",
    "Cloud computing revolutionizes how we deploy applications.",
    "Artificial intelligence is transforming industries globally.",
    "Distributed systems enable scalable applications.",
    "Containerization with Docker simplifies deployment.",
    "The rapid advancement in technology continues to reshape society.",
    "Data science combines statistics and programming for insights.",
    "Microservices architecture allows independent service scaling.",
]


def submit_job(text: str) -> dict:
    """Submit a single plagiarism detection job."""
    try:
        response = requests.post(
            f"{API_URL}/submit",
            json={"text": text},
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"✗ Submit failed: {e}")
        return None


def check_result(job_id: str) -> dict:
    """Check result of a job."""
    try:
        response = requests.get(
            f"{API_URL}/result/{job_id}",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"✗ Get result failed: {e}")
        return None


def stress_test(num_jobs: int = 20, num_workers: int = 5):
    """
    Submit multiple jobs and monitor their progress.
    
    Args:
        num_jobs: Number of jobs to submit
        num_workers: Number of concurrent submission threads
    """
    print(f"🚀 Starting stress test: {num_jobs} jobs with {num_workers} threads")
    print(f"📍 API: {API_URL}\n")
    
    job_ids = []
    
    # Phase 1: Submit all jobs
    print(f"[Phase 1] Submitting {num_jobs} jobs...")
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for i in range(num_jobs):
            text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
            future = executor.submit(submit_job, text)
            futures.append(future)
        
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                job_ids.append(result['job_id'])
                print(f"  ✓ Job {i+1}/{num_jobs} submitted: {result['job_id'][:8]}...")
    
    submit_time = time.time() - start_time
    print(f"✓ All jobs submitted in {submit_time:.2f}s\n")
    
    # Phase 2: Check queue stats
    try:
        response = requests.get(f"{API_URL}/queue/stats")
        stats = response.json()
        print(f"📊 Queue Stats: {stats['message']}\n")
    except:
        pass
    
    # Phase 3: Monitor job completion
    print(f"[Phase 2] Monitoring {len(job_ids)} jobs for completion...")
    completed = 0
    failed = 0
    max_wait = 120  # 2 minutes max
    check_interval = 2  # Check every 2 seconds
    elapsed = 0
    
    while completed + failed < len(job_ids) and elapsed < max_wait:
        time.sleep(check_interval)
        elapsed += check_interval
        
        for job_id in job_ids:
            if job_id is None:
                continue
            
            result = check_result(job_id)
            if result:
                status = result.get('status', 'UNKNOWN')
                
                if status == 'COMPLETED':
                    score = result.get('result', {}).get('max_plagiarism_score', 'N/A')
                    print(f"  ✓ {job_id[:8]}... COMPLETED (score: {score})")
                    completed += 1
                    job_ids[job_ids.index(job_id)] = None  # Mark as processed
                elif status == 'FAILED':
                    print(f"  ✗ {job_id[:8]}... FAILED")
                    failed += 1
                    job_ids[job_ids.index(job_id)] = None
    
    # Phase 4: Results summary
    total_time = time.time() - start_time
    pending = len(job_ids) - completed - failed
    
    print(f"\n📈 Results Summary:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Completed: {completed}/{len(job_ids)}")
    print(f"  Failed: {failed}/{len(job_ids)}")
    print(f"  Pending: {pending}/{len(job_ids)}")
    print(f"  Avg time per job: {total_time/len(job_ids):.2f}s")
    print(f"  Throughput: {len(job_ids)/total_time:.2f} jobs/sec")


if __name__ == "__main__":
    num_jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    try:
        stress_test(num_jobs, num_workers)
    except KeyboardInterrupt:
        print("\n⏹ Stress test interrupted")
    except Exception as e:
        print(f"\n✗ Error: {e}")
