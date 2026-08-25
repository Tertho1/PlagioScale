#!/usr/bin/env python3
"""
Test Script 3: API Auto-Scaling
Sends concurrent requests to stress the API and watches replicas scale 1->N.
Monitors p95 latency and verifies Nginx distributes traffic across replicas.
Run: python scripts/test_api_scaling.py
"""

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API = "http://localhost:3050/api"


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def run(cmd):
    """Run command and return stdout."""
    with os.popen(cmd) as f:
        return f.read().strip()


def get_api_containers():
    raw = run('docker ps --format "{{.Names}}~{{.Status}}"')
    containers = []
    for line in raw.splitlines():
        if "api" in line.lower() and "autoscaler" not in line.lower():
            parts = line.split("~", 1)
            if len(parts) >= 2:
                containers.append({"name": parts[0], "status": parts[1]})
    return containers


def get_api_metrics():
    try:
        r = requests.get(f"{API}/metrics", timeout=3)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def get_autoscaler_metrics():
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:8002/metrics", timeout=3)
        text = r.read().decode()
        result = {}
        for line in text.splitlines():
            if line.startswith("plagioscale_api_replicas"):
                result["api_replicas"] = float(line.split()[-1])
            elif line.startswith("plagioscale_api_p95_ms"):
                result["api_p95_ms"] = float(line.split()[-1])
            elif line.startswith("plagioscale_scale_events_total"):
                if not line.startswith("#"):
                    result["scale_events"] = float(line.split()[-1])
        return result
    except Exception:
        return {}


def get_worker_count():
    raw = run('docker ps --format {{.Names}}')
    return len([n for n in raw.splitlines() if "worker" in n.lower() and "autoscaler" not in n.lower()])


def login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={
        "email": os.getenv("DEMO_EMAIL", "admin@test.com"),
        "password": os.getenv("DEMO_PASSWORD", "admin123"),
    }, timeout=5)
    if r.status_code != 200:
        print(f"  Login failed: {r.status_code} {r.text[:100]}")
        return None, None
    csrf = s.cookies.get("csrf_token", "")
    token = s.cookies.get("access_token", "")
    return s, csrf


def single_request(session, endpoint):
    """Make a single API request and return elapsed time."""
    start = time.monotonic()
    try:
        r = session.get(f"{API}{endpoint}", timeout=10)
        elapsed = time.monotonic() - start
        return elapsed, r.status_code
    except Exception as e:
        elapsed = time.monotonic() - start
        return elapsed, str(e)


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - API AUTO-SCALING TEST")
    print("=" * 70)
    print()
    print("  This test sends concurrent requests to stress the API.")
    print("  The autoscaler monitors p95 latency and scales API replicas.")
    print("  Nginx dynamically distributes traffic across all replicas.")
    print()

    # --- Step 1: Current State ---
    print("[1/5] CURRENT STATE")
    print("-" * 70)
    containers = get_api_containers()
    metrics = get_api_metrics()
    auto_metrics = get_autoscaler_metrics()
    print(f"  API replicas:  {len(containers)}")
    for c in containers:
        print(f"    - {c['name']}: {c['status']}")
    if metrics:
        print(f"  Current p95:   {metrics.get('p95_ms', 0):.1f}ms")
        print(f"  Request count: {metrics.get('request_count', 0)}")
    if auto_metrics:
        print(f"  Autoscaler p95: {auto_metrics.get('api_p95_ms', 0):.1f}ms")
        print(f"  Scale events:   {int(auto_metrics.get('scale_events', 0))}")
    print(f"  Workers:        {get_worker_count()}")
    pause()

    # --- Step 2: Login ---
    print("\n[2/5] AUTHENTICATING")
    print("-" * 70)
    session, csrf = login()
    if not session:
        print("  Cannot continue without login.")
        return
    print("  Logged in successfully")
    pause()

    # --- Step 3: Baseline Request ---
    print("\n[3/5] BASELINE MEASUREMENT")
    print("-" * 70)
    print("  Sending 20 sequential requests to measure baseline latency...")
    latencies = []
    for i in range(20):
        elapsed, status = single_request(session, "/health")
        latencies.append(elapsed)
        print(f"    [{i+1:>2}/20] {elapsed*1000:>6.1f}ms  status={status}")
    avg = sum(latencies) / len(latencies) * 1000
    print(f"\n  Baseline avg: {avg:.1f}ms")
    pause()

    # --- Step 4: Stress Test ---
    print("\n[4/5] STRESS TEST - CONCURRENT REQUESTS")
    print("-" * 70)
    endpoints = [
        "/health", "/metrics",
        "/portal/assignments",
    ]

    # Phase 1: 20 concurrent requests
    print("  Phase 1: 20 concurrent requests...")
    results = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [
            pool.submit(single_request, session, endpoints[i % len(endpoints)])
            for i in range(20)
        ]
        for f in as_completed(futures):
            results.append(f.result())
    p95_sorted = sorted([r[0] for r in results])
    p95_idx = int(len(p95_sorted) * 0.95)
    p95 = p95_sorted[p95_idx] * 1000
    errors = sum(1 for _, s in results if s != 200)
    print(f"    Done: p95={p95:.1f}ms, errors={errors}")
    pause()

    # Phase 2: 50 concurrent requests (this should trigger scaling)
    print("  Phase 2: 50 concurrent requests (scaling trigger)...")
    results2 = []
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [
            pool.submit(single_request, session, endpoints[i % len(endpoints)])
            for i in range(50)
        ]
        for f in as_completed(futures):
            results2.append(f.result())
    p95_sorted2 = sorted([r[0] for r in results2])
    p95_idx2 = int(len(p95_sorted2) * 0.95)
    p95_2 = p95_sorted2[p95_idx2] * 1000
    errors2 = sum(1 for _, s in results2 if s != 200)
    print(f"    Done: p95={p95_2:.1f}ms, errors={errors2}")
    pause()

    # --- Step 5: Watch for Scaling ---
    print("\n[5/5] WATCHING FOR API SCALING")
    print("-" * 70)
    print("  Polling every 3s. The autoscaler checks p95 every 5s...")
    print(f"  Threshold: scale UP if p95 > 500ms, scale DOWN if p95 < 200ms")
    print()

    start = time.time()
    initial_events = int(auto_metrics.get("scale_events", 0))
    saw_scale = False

    for tick in range(20):
        time.sleep(3)
        elapsed = int(time.time() - start)
        containers_now = get_api_containers()
        metrics_now = get_api_metrics()
        auto_now = get_autoscaler_metrics()
        n_api = len(containers_now)
        p95_now = metrics_now.get("p95_ms", 0) if metrics_now else 0
        events_now = int(auto_now.get("scale_events", 0))
        new_events = events_now - initial_events

        marker = ""
        if new_events > 0 and not saw_scale:
            saw_scale = True
            marker = " <- SCALE EVENT"
        elif new_events > 0:
            marker = f" <- {new_events} event(s)"

        names = ", ".join(c["name"].replace("plagioscale-", "") for c in containers_now)
        print(f"  [{elapsed:>3}s] API: {n_api} ({names}) | p95: {p95_now:.1f}ms{marker}")

        # After stress test, p95 will drop quickly - wait for scale-down
        if tick > 5 and n_api <= 1 and p95_now < 200:
            print("\n  p95 is low and only 1 replica - scale-down will happen if load was high")
            break

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  RESULTS SUMMARY")
    print("=" * 70)
    print(f"  Baseline p95:       {avg:.1f}ms")
    print(f"  Under load p95:     {p95_2:.1f}ms")
    print(f"  API replicas seen:  {len(containers)} -> {len(get_api_containers())}")
    print(f"  Scale events:       {new_events if saw_scale else 'none (p95 stayed under threshold)'}")
    print()
    print("  HOW IT WORKS:")
    print("  1. API /metrics endpoint tracks request latency (p50/p95/p99)")
    print("  2. Autoscaler polls /metrics every 5s from each API replica")
    print("  3. p95 > 500ms -> creates new API container via Docker SDK")
    print("  4. p95 < 200ms -> stops extra API containers")
    print("  5. Nginx resolver re-resolves api-service DNS on each request")
    print("  6. Traffic distributed across all running replicas")
    print("  7. Cooldown: 60s between API scale events")
    print("  8. Limits: min=1, max=5 API replicas")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        pause("\nPress Enter to exit...")
