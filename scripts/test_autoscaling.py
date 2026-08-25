#!/usr/bin/env python3
"""
Demo Script 2: Queue-Based Autoscaling
Submits jobs rapidly and watches workers scale from 1 -> N.
Run: python scripts/demo_autoscaling.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

import redis
import requests

API = os.getenv("API_URL", "http://localhost:3050/api")
REDIS = redis.Redis(host="localhost", port=6379, decode_responses=True, password=os.getenv("REDIS_PASSWORD", "plagio_redis_pass"))

SAMPLE_TEXTS = [
    "Machine learning is a powerful tool for data analysis and prediction in modern computing.",
    "Cloud computing revolutionizes how we deploy and scale applications across infrastructure.",
    "Artificial intelligence is transforming industries globally through automation and decisions.",
    "Distributed systems enable scalable applications by partitioning work across multiple nodes.",
    "Containerization with Docker simplifies deployment by packaging apps with dependencies.",
    "The rapid advancement in technology continues to reshape society and digital interactions.",
    "Data science combines statistics and programming to extract insights from complex datasets.",
    "Microservices architecture allows independent scaling of services with loose coupling.",
    "Natural language processing enables computers to understand and generate human language.",
    "Cybersecurity frameworks protect organizations from evolving threats through layered defense.",
    "Machine learning models identify patterns in data that humans might overlook during analysis.",
    "Cloud-native applications leverage containers and orchestration for resilient deployment.",
    "Deep learning networks achieve remarkable results in image and language recognition tasks.",
    "Agile development methodologies emphasize iterative progress through team collaboration.",
    "Blockchain technology provides decentralized consensus for trustless transaction verification.",
    "Edge computing brings computation closer to data sources reducing latency for real-time apps.",
    "Quantum computing promises to solve problems intractable for classical computers someday.",
    "DevOps practices bridge development and operations through automation and monitoring.",
    "Serverless computing abstracts infrastructure management away from application developers.",
    "5G networks enable new possibilities for IoT and real-time communication at scale.",
]


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def get_workers():
    raw = subprocess.run(
        "docker ps --format {{.Names}}",
        shell=True, capture_output=True, text=True
    ).stdout.strip()
    return [n for n in raw.splitlines() if "worker" in n.lower() and "autoscaler" not in n.lower()]


def get_queue_depth():
    try:
        return REDIS.llen("job_queue")
    except Exception:
        return -1


def login():
    """Login and return cookies + CSRF token."""
    s = requests.Session()
    # Get CSRF token from login page
    r = s.get(f"{API}/auth/login", timeout=5)
    csrf = s.cookies.get("csrf_token", "")
    # Login
    r = s.post(f"{API}/auth/login", json={
        "email": os.getenv("DEMO_EMAIL", "admin@test.com"),
        "password": os.getenv("DEMO_PASSWORD", "admin123"),
    }, headers={"X-CSRF-Token": csrf}, timeout=5)
    if r.status_code != 200:
        print(f"  [--] Login failed: {r.status_code} {r.text[:100]}")
        return None, None
    csrf = s.cookies.get("csrf_token", "")
    return s, csrf


def create_batch(session, csrf, name):
    """Create a temporary assignment and return batch_id."""
    r = session.post(f"{API}/portal/assignments", json={
        "name": name,
        "expected_count": 20,
    }, headers={"X-CSRF-Token": csrf}, timeout=5)
    if r.status_code != 200:
        print(f"  [--] Create batch failed: {r.status_code}")
        return None
    return r.json().get("batch_id")


def submit_file(session, csrf, batch_id, roll, text):
    """Submit a text file to a batch."""
    # Create temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(text)
        tmp_path = f.name
    try:
        with open(tmp_path, "rb") as f:
            r = session.post(f"{API}/portal/submit", data={
                "batch_id": batch_id,
                "roll": roll,
                "name": f"Student {roll}",
                "email": f"{roll}@test.com",
            }, files={"file": (f"{roll}.txt", f, "text/plain")},
            headers={"X-CSRF-Token": csrf}, timeout=10)
        return r.status_code == 200
    finally:
        os.unlink(tmp_path)


def cleanup_batch(session, csrf, batch_id):
    """Delete a temporary batch."""
    if session and batch_id:
        try:
            session.delete(f"{API}/portal/assignments/{batch_id}",
                           headers={"X-CSRF-Token": csrf}, timeout=5)
        except Exception:
            pass


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - AUTOSCALING DEMO")
    print("=" * 70)
    print()
    print("  This demo shows how the autoscaler reacts to queue depth.")
    print("  When jobs pile up in Redis, new worker containers spin up.")
    print("  When the queue drains, workers scale back down.")
    print()

    # --- Step 1: Current State ---
    print("[1/5] CURRENT STATE")
    print("-" * 70)
    workers = get_workers()
    queue = get_queue_depth()
    print(f"  Workers running: {len(workers)} - {', '.join(workers)}")
    print(f"  Queue depth:     {queue} jobs")
    pause()

    # --- Step 2: Login & Create Batch ---
    print("\n[2/5] SETTING UP TEST BATCH")
    print("-" * 70)
    session, csrf = login()
    if not session:
        print("  [--] Cannot continue without login. Set DEMO_EMAIL/DEMO_PASSWORD env vars.")
        return
    print("  [OK] Logged in")

    batch_id = create_batch(session, csrf, "Autoscale Demo")
    if not batch_id:
        print("  [--] Cannot create batch")
        return
    print(f"  [OK] Created batch: {batch_id[:8]}...")

    # Submit files
    print("  Submitting 10 files...")
    for i in range(10):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        ok = submit_file(session, csrf, batch_id, f"AS{i+1:03d}", text)
        status = "[OK]" if ok else "[--]"
        print(f"    {status} Submission {i+1}/10")
    pause()

    # --- Step 3: Enqueue Jobs ---
    print("\n[3/5] ENQUEUING JOBS")
    print("-" * 70)
    # Enqueue 15 BATCH_COMPUTE jobs directly to Redis
    for i in range(15):
        job_id = f"demo-{batch_id[:8]}-{i:03d}"
        payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
        job = json.dumps({"job_id": job_id, "text": payload})
        REDIS.lpush("job_queue", job)
    queue_after = get_queue_depth()
    print(f"  [OK] Enqueued 15 jobs -> queue depth now: {queue_after}")
    pause()

    # --- Step 4: Watch Scaling ---
    print("\n[4/5] WATCHING AUTOSCALER REACT")
    print("-" * 70)
    print("  Polling every 3s. Watch for new worker containers to appear...")
    print()
    max_workers = len(workers)
    scale_events = []
    start = time.time()

    for tick in range(30):  # Poll for up to 90 seconds
        time.sleep(3)
        current_workers = get_workers()
        queue_depth = get_queue_depth()
        elapsed = int(time.time() - start)

        n_workers = len(current_workers)
        if n_workers > max_workers:
            new = set(current_workers) - set(workers)
            scale_events.append(("UP", elapsed, n_workers, new))
            max_workers = n_workers

        marker = " <- SCALE UP" if n_workers > len(workers) else ""
        print(f"  [{elapsed:>3}s] Workers: {n_workers} | Queue: {queue_depth:>3}{marker}")

        if queue_depth == 0 and tick > 3:
            print("\n  [OK] Queue drained - autoscaler will scale down shortly")
            break

    # Wait for scale-down
    print("\n  Waiting for scale-down...")
    for _ in range(10):
        time.sleep(3)
        current_workers = get_workers()
        queue_depth = get_queue_depth()
        n_workers = len(current_workers)
        print(f"  Workers: {n_workers} | Queue: {queue_depth}")
        if n_workers <= 1 and queue_depth == 0:
            break

    # --- Step 5: Summary ---
    print("\n[5/5] SUMMARY")
    print("-" * 70)
    print(f"  Max workers observed:  {max_workers}")
    print(f"  Scale-up events:       {len(scale_events)}")
    print(f"  Time to drain queue:   {int(time.time() - start)}s")
    if scale_events:
        for direction, t, nw, details in scale_events:
            print(f"    ^ t={t}s: scaled to {nw} workers")
    print()
    print("  HOW IT WORKS:")
    print("  1. Autoscaler polls Redis queue depth every 5s")
    print("  2. Queue > 10 -> creates new worker via Docker SDK")
    print("  3. Queue < 3 -> stops extra workers")
    print("  4. Cooldown: 20s between scale events")
    print("  5. Limits: min=1, max=5 workers")
    print("=" * 70)

    # Cleanup
    print("\nCleaning up...")
    cleanup_batch(session, csrf, batch_id)
    print("  [OK] Demo batch deleted")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Cleaning up...")
    finally:
        pause("\nPress Enter to exit...")
