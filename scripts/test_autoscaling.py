#!/usr/bin/env python3
"""
Demo Script 2: Queue-Based Autoscaling
Submits jobs rapidly and watches workers scale from 1 → N.
Run: python scripts/demo_autoscaling.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import redis
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://localhost:3050/api"
REDIS = redis.Redis(
    host="localhost", port=6379,
    password=os.getenv("REDIS_PASSWORD", "plagio_redis_pass"),
    decode_responses=True,
)

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


def _run_with_retry(cmd, retries=4, delay=2):
    """subprocess.run with retry — survives transient WinError 1455
    (commit-limit spikes while worker containers are warming models)."""
    last = None
    for attempt in range(retries):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        except OSError as e:
            last = e
            time.sleep(delay)
    raise last


def get_workers():
    raw = _run_with_retry(
        "docker ps --format {{.Names}}"
    ).stdout.strip()
    return [n for n in raw.splitlines() if "worker" in n.lower() and "autoscaler" not in n.lower()]


def get_queue_depth():
    try:
        return REDIS.llen("job_queue")
    except Exception:
        return -1


def login():
    """Login and return a session with Bearer auth + CSRF cookie."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={
        "email": os.getenv("DEMO_EMAIL", "admin@test.com"),
        "password": os.getenv("DEMO_PASSWORD", "admin123"),
    }, timeout=5)
    if r.status_code != 200:
        print(f"  ✗ Login failed: {r.status_code} {r.text[:100]}")
        return None, None
    token = r.json().get("access_token", "")
    s.headers["Authorization"] = f"Bearer {token}"
    csrf = s.cookies.get("csrf_token", "")
    if csrf:
        s.headers["X-CSRF-Token"] = csrf
    return s, csrf


def create_batch(session, csrf, name):
    """Create a temporary assignment and return batch_id."""
    r = session.post(f"{API}/portal/assignments", json={
        "name": name,
        "expected_count": 20,
    }, timeout=5)
    if r.status_code != 200:
        print(f"  ✗ Create batch failed: {r.status_code}")
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
            timeout=10)
        return r.status_code == 200
    finally:
        os.unlink(tmp_path)


def cleanup_batch(session, csrf, batch_id):
    """Delete a temporary batch."""
    if session and batch_id:
        try:
            session.delete(f"{API}/portal/assignments/{batch_id}", timeout=5)
        except Exception:
            pass


def main():
    print("=" * 70)
    print("  PLAGIOSCALE — AUTOSCALING DEMO")
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
    print(f"  Workers running: {len(workers)} — {', '.join(workers)}")
    print(f"  Queue depth:     {queue} jobs")
    pause()

    # --- Step 2: Login & Create Batch ---
    print("\n[2/5] SETTING UP TEST BATCH")
    print("-" * 70)
    session, csrf = login()
    if not session:
        print("  ✗ Cannot continue without login. Set DEMO_EMAIL/DEMO_PASSWORD env vars.")
        return
    print("  ✓ Logged in")

    batch_id = create_batch(session, csrf, "Autoscale Demo")
    if not batch_id:
        print("  ✗ Cannot create batch")
        return
    print(f"  ✓ Created batch: {batch_id[:8]}...")

    # Submit files
    print("  Submitting 10 files...")
    for i in range(10):
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
        ok = submit_file(session, csrf, batch_id, f"AS{i+1:03d}", text)
        status = "✓" if ok else "✗"
        print(f"    {status} Submission {i+1}/10")
    pause()

    # --- Step 3: Enqueue Jobs ---
    print("\n[3/5] ENQUEUING JOBS")
    print("-" * 70)
    JOBS = int(os.getenv("DEMO_JOBS", "100"))
    # Enqueue BATCH_COMPUTE jobs directly to Redis (full Job.to_json shape)
    for i in range(JOBS):
        job_id = f"demo-{batch_id[:8]}-{i:03d}"
        payload = json.dumps({"type": "BATCH_COMPUTE", "batch_id": batch_id})
        job = json.dumps({
            "job_id": job_id,
            "text": payload,
            "status": "PENDING",
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        })
        REDIS.lpush("job_queue", job)
    queue_after = get_queue_depth()
    print(f"  ✓ Enqueued {JOBS} jobs → queue depth now: {queue_after}")
    pause()

    # --- Step 4: Watch Scaling ---
    print("\n[4/5] WATCHING AUTOSCALER REACT")
    print("-" * 70)
    up_th, down_th, cap = 10, 3, int(os.getenv("MAX_WORKERS", "3"))
    cd_s = int(os.getenv("COOLDOWN_SECONDS", "10"))
    print(f"  Rule: queue > {up_th} → scale up | queue < {down_th} → scale down")
    print(f"  Limits: min 1 / max {cap} workers | Cooldown: {cd_s}s between events\n")

    known = set(get_workers())
    max_seen = len(known)
    scale_events = []
    threshold_announced = False
    last_event_t = None
    start = time.time()
    deadline = start + 480

    while time.time() < deadline:
        time.sleep(3)
        now_list = get_workers()
        queue_depth = get_queue_depth()
        n = len(now_list)
        elapsed = int(time.time() - start)

        if n > len(known):
            new = sorted(set(now_list) - known)
            known = set(now_list)
            max_seen = max(max_seen, n)
            scale_events.append(("UP", elapsed, n))
            last_event_t = elapsed
            print(f"  [{elapsed:>3}s] ▲ SCALE UP   → {n} workers (+{', '.join(new)}) | Queue: {queue_depth}")

        elif n < len(known):
            gone = sorted(known - set(now_list))
            known = set(now_list)
            scale_events.append(("DOWN", elapsed, n))
            last_event_t = elapsed
            print(f"  [{elapsed:>3}s] ▼ SCALE DOWN → {n} workers (-{', '.join(gone)}) | Queue: {queue_depth}")

        else:
            if queue_depth > up_th and not threshold_announced:
                print(f"  [{elapsed:>3}s] ⚠ Queue depth {queue_depth} exceeds threshold ({up_th})")
                threshold_announced = True
            elif queue_depth <= down_th:
                threshold_announced = False

            if queue_depth == 0 and n == 1:
                print(f"  [{elapsed:>3}s] Workers: {n}/{cap} | Queue: {queue_depth} — settled at baseline")
                break

            cooling = last_event_t is not None and (elapsed - last_event_t) < cd_s
            note = ""
            if n < cap and queue_depth > up_th:
                note = (f" | ⏳ scale-up pending (cooldown {cd_s - (elapsed - last_event_t):.0f}s left)"
                        if cooling else " | ⏳ scale-up pending (next autoscaler tick)")
            elif n > 1 and queue_depth < down_th:
                note = (" | ⏳ scale-down pending (cooldown)" if cooling
                        else " | ⏳ scale-down pending (graceful stop / next tick)")
            print(f"  [{elapsed:>3}s] Workers: {n}/{cap} | Queue: {queue_depth:>3}{note}")

    # --- Step 5: Summary ---
    ups = [(t, w) for d, t, w in scale_events if d == "UP"]
    downs = [(t, w) for d, t, w in scale_events if d == "DOWN"]
    print("\n[5/5] SUMMARY")
    print("-" * 70)
    print(f"  Max workers observed: {max_seen}")
    print(f"  Scale-up events:      {len(ups)}" +
          ("   " + ", ".join(f"t+{t}s→{w}" for t, w in ups) if ups else ""))
    print(f"  Scale-down events:    {len(downs)}" +
          ("   " + ", ".join(f"t+{t}s→{w}" for t, w in downs) if downs else ""))
    print(f"  Total time:           {int(time.time() - start)}s")
    print()
    print("  HOW IT WORKS:")
    print("  1. Autoscaler polls Redis queue depth every 5s")
    print("  2. Queue > 10 → creates new worker via Docker SDK")
    print("  3. Queue < 3 → stops extra workers")
    print(f"  4. Cooldown: {cd_s}s between scale events")
    print(f"  5. Limits: min=1, max={cap} workers on this machine")
    print("=" * 70)

    # Cleanup
    print("\nCleaning up...")
    cleanup_batch(session, csrf, batch_id)
    print("  ✓ Demo batch deleted")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Cleaning up...")
    finally:
        pause("\nPress Enter to exit...")
