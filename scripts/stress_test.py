"""
Stress testing script - simulates multiple plagiarism detection requests.
Includes autoscaling verification phase.
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

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
        print(f"\u2717 Submit failed: {e}")
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
        print(f"\u2717 Get result failed: {e}")
        return None


def check_autoscaler_state():
    """Query the monitoring service for current cluster state."""
    results = {}
    try:
        resp = requests.get("http://localhost:8090/api/overview", timeout=5)
        if resp.ok:
            data = resp.json()
            results["monitor"] = {
                "workers": data.get("workers", 0),
                "queue_length": data.get("queue_length", 0),
                "jobs": data.get("jobs", {}),
            }
            print(f"  \u2139 Monitor: {resp.status_code} OK ({data.get('workers', '?')} workers, {data.get('queue_length', '?')} queued)")
        else:
            print(f"  \u26a0 Monitor: {resp.status_code}")
    except Exception as e:
        print(f"  \u2014 Monitor: not reachable ({e})")
    return results


def stress_test(num_jobs: int = 20, num_workers: int = 5):
    """
    Submit multiple jobs and monitor their progress.

    Args:
        num_jobs: Number of jobs to submit
        num_workers: Number of concurrent submission threads
    """
    print(f"Starting stress test: {num_jobs} jobs with {num_workers} threads")
    print(f"API: {API_URL}\n")

    job_ids = []

    # Phase 1: Pre-test autoscaler state
    print("[Phase 0] Checking autoscaler state before test...")
    pre_scale = check_autoscaler_state()
    print()

    # Phase 2: Submit all jobs
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
                print(f"  \u2713 Job {i+1}/{num_jobs} submitted: {result['job_id'][:8]}...")

    submit_time = time.time() - start_time
    print(f"\u2713 All jobs submitted in {submit_time:.2f}s\n")

    # Phase 3: Check queue stats
    try:
        response = requests.get(f"{API_URL}/queue/stats")
        stats = response.json()
        print(f"Queue Stats: {stats['message']}\n")
    except:
        pass

    # Phase 4: Monitor job completion
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
                    print(f"  \u2713 {job_id[:8]}... COMPLETED (score: {score})")
                    completed += 1
                    job_ids[job_ids.index(job_id)] = None  # Mark as processed
                elif status == 'FAILED':
                    print(f"  \u2717 {job_id[:8]}... FAILED")
                    failed += 1
                    job_ids[job_ids.index(job_id)] = None

    # Phase 5: Autoscaling verification
    print("\n[Phase 3] Verifying autoscaler response...")
    time.sleep(2)
    post_scale = check_autoscaler_state()
    _report_scale_change(pre_scale, post_scale)

    # Phase 6: Results summary
    total_time = time.time() - start_time
    pending = len(job_ids) - completed - failed

    print("\nResults Summary:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Completed: {completed}/{len(job_ids)}")
    print(f"  Failed: {failed}/{len(job_ids)}")
    print(f"  Pending: {pending}/{len(job_ids)}")
    print(f"  Avg time per job: {total_time/len(job_ids):.2f}s")
    print(f"  Throughput: {len(job_ids)/total_time:.2f} jobs/sec")

    if completed >= num_jobs * 0.8:
        print("\n  STRESS TEST PASSED (>=80% jobs completed)")
    else:
        print("\n  STRESS TEST FAILED (<80% jobs completed)")


def _report_scale_change(pre, post):
    """Compare pre/post autoscaler snapshots."""
    print("\n  Autoscaler comparison:")
    for key in pre:
        before = pre.get(key, {})
        after = post.get(key, {})
        workers_before = before.get("workers", "?")
        workers_after = after.get("workers", "?")
        if workers_before != workers_after:
            print(f"    \u2191 {key}: {workers_before} \u2192 {workers_after} workers")
        else:
            print(f"    \u2014 {key}: {workers_before} workers (unchanged)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PlagioScale stress test with autoscaling verification")
    parser.add_argument("num_jobs", nargs="?", type=int, default=20, help="Number of jobs to submit (default: 20)")
    parser.add_argument("num_workers", nargs="?", type=int, default=5, help="Concurrent submission threads (default: 5)")
    parser.add_argument("--scale", type=int, metavar="N", help="Pre-scale workers to N before test")
    args = parser.parse_args()

    if args.scale:
        print(f"[Setup] Requesting pre-scale to {args.scale} workers...")
        try:
            resp = requests.post(f"{API_URL}/portal/admin/scale/{args.scale}", timeout=5)
            if resp.ok:
                print(f"  ✓ Pre-scaled to {args.scale} workers")
            else:
                print(f"  ⚠ Pre-scale request returned {resp.status_code}")
        except requests.ConnectionError:
            print("  — Autoscaler endpoint not reachable, proceeding without pre-scale")
        time.sleep(2)

    try:
        stress_test(args.num_jobs, args.num_workers)
    except KeyboardInterrupt:
        print("\nStress test interrupted")
    except Exception as e:
        print(f"\nError: {e}")
