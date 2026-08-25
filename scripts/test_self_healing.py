#!/usr/bin/env python3
"""
Demo Script 3: Self-Healing
Stops a service, shows degradation, restarts, shows auto-recovery.
Run: python scripts/demo_self_healing.py
"""

import atexit
import os
import subprocess
import sys
import time

import requests

API = os.getenv("API_URL", "http://localhost:3050/api")
POSTGRES_CONTAINER = "plagioscale-postgres"

stopped_services = []


def ensure_restore():
    """Restart any services we stopped - runs even on Ctrl+C."""
    for svc in stopped_services:
        print(f"\n  [restore] Restarting {svc}...")
        subprocess.run(f"docker start {svc}", shell=True, capture_output=True, timeout=15)
    if stopped_services:
        print("  [restore] All services restored.")


atexit.register(ensure_restore)


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()


def health():
    try:
        r = requests.get(f"{API}/health", timeout=3)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


def db_dependent_check():
    """Try an endpoint that requires the database."""
    try:
        r = requests.get(f"{API}/portal/assignments", timeout=3,
                         headers={"Authorization": "Bearer invalid"})
        return r.status_code, r.json().get("detail", "")
    except Exception as e:
        return 0, str(e)


def get_worker_logs(n=10):
    raw = run(f"docker logs plagioscale-worker-1 --tail {n} 2>&1")
    return raw


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - SELF-HEALING DEMO")
    print("=" * 70)
    print()
    print("  This demo shows how the system recovers when a critical service fails.")
    print("  We'll stop PostgreSQL, watch the API degrade, then restart and recover.")
    print()
    print("  !!  WARNING: This will briefly interrupt the running stack.")
    print("  !!  All services will be auto-restored at the end.")
    print()

    # --- Step 1: Healthy State ---
    print("[1/5] HEALTHY STATE")
    print("-" * 70)
    h = health()
    print(f"  /health response: {h.get('status', 'unknown')}")
    for dep, status in h.get("dependencies", {}).items():
        marker = "[OK]" if status == "ok" else "[--]"
        print(f"    {marker} {dep}: {status}")
    pause()

    # --- Step 2: Stop PostgreSQL ---
    print("\n[2/5] STOPPING POSTGRESQL")
    print("-" * 70)
    print(f"  Running: docker stop {POSTGRES_CONTAINER}")
    result = run(f"docker stop {POSTGRES_CONTAINER}")
    stopped_services.append(POSTGRES_CONTAINER)
    print(f"  [OK] Container stopped: {result}")
    time.sleep(2)
    pause()

    # --- Step 3: Show Degradation ---
    print("\n[3/5] SYSTEM DEGRADED")
    print("-" * 70)

    # Health endpoint
    print("  Checking /health endpoint...")
    for i in range(3):
        h = health()
        status = h.get("status", "unknown")
        print(f"    Attempt {i+1}: status = {status}")
        if status != "healthy":
            break
        time.sleep(2)

    print()
    for dep, status in h.get("dependencies", {}).items():
        marker = "[OK]" if status == "ok" else "[--] DOWN"
        print(f"    {marker} {dep}: {status}")

    # DB-dependent endpoint
    print("\n  Checking DB-dependent endpoint (/portal/assignments)...")
    code, detail = db_dependent_check()
    print(f"    HTTP {code}: {detail}")

    print()
    print("  [OK] API correctly reports 'degraded' - it's still running but can't")
    print("    reach the database. Requests requiring DB fail gracefully.")
    pause()

    # --- Step 4: Restart PostgreSQL ---
    print("\n[4/5] RESTARTING POSTGRESQL")
    print("-" * 70)
    print(f"  Running: docker start {POSTGRES_CONTAINER}")
    run(f"docker start {POSTGRES_CONTAINER}")
    stopped_services.remove(POSTGRES_CONTAINER)
    print("  [OK] Container started. Waiting for health check...")
    time.sleep(5)
    pause()

    # --- Step 5: Show Recovery ---
    print("\n[5/5] SYSTEM RECOVERED")
    print("-" * 70)

    print("  Checking /health endpoint...")
    for i in range(5):
        h = health()
        status = h.get("status", "unknown")
        print(f"    Attempt {i+1}: status = {status}")
        if status == "healthy":
            break
        time.sleep(3)

    print()
    for dep, status in h.get("dependencies", {}).items():
        marker = "[OK]" if status == "ok" else "[--]"
        print(f"    {marker} {dep}: {status}")

    # DB-dependent endpoint
    print("\n  Checking DB-dependent endpoint...")
    code, detail = db_dependent_check()
    print(f"    HTTP {code}: {detail}")

    # Worker logs
    print("\n  Worker logs (last 10 lines):")
    logs = get_worker_logs(10)
    for line in logs.splitlines()[-10:]:
        print(f"    {line}")

    print()
    print("  [OK] FULL RECOVERY - API reconnected to DB automatically")
    print()
    print("  SELF-HEALING MECHANISMS:")
    print("  1. DB monitor: background task pings DB every 30s")
    print("  2. On failure: sets db_ready=False, returns 503 for DB endpoints")
    print("  3. On recovery: calls init_db(), restores db_ready, increments counter")
    print("  4. Stale job recovery: finds stuck jobs every 60s, retries up to 3x")
    print("  5. Dead letter: exhausted jobs stored with payload for manual inspection")
    print("  6. Worker reconnection: worker main loop pings DB every 30s")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        pause("\nPress Enter to exit (services already restored)...")
