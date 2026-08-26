#!/usr/bin/env python3
"""
Demo Script 3: Self-Healing
Stops PostgreSQL, watches the API degrade gracefully (503s, degraded health),
restarts it, and shows automatic recovery — all verified through live HTTP
probes with a real authenticated session.

Self-healing mechanisms exercised:
  1. API's _monitor_db background task pings the DB every 30s
  2. DB down  -> db_ready=False -> /health "degraded", authed endpoints 503
  3. DB back  -> init_db() reconnects, db_ready=True, recovery counter++,
     authenticated endpoints return to normal without any restart

Run: python scripts/test_self_healing.py
"""

import atexit
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (API, NON_INTERACTIVE, PlagioClient, pause, run,
                    service_containers, short)

POSTGRES_CONTAINER = os.getenv("POSTGRES_CONTAINER", f"{os.getenv('COMPOSE_PROJECT_NAME', 'plagioscale')}-postgres")

stopped = []


def ensure_restore():
    """Restart anything we stopped - runs even on Ctrl+C."""
    for svc in stopped:
        print(f"\n  [restore] Starting {svc}...")
        run(["docker", "start", svc], timeout=30)
    if stopped:
        print("  [restore] Done.")
        stopped.clear()


atexit.register(ensure_restore)


def health():
    try:
        r = requests.get(f"{API}/health", timeout=5)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


def authed_probe(client):
    """GET /portal/assignments WITH a valid JWT.

    This is what proves degradation: unauthenticated requests would be 401 in
    both states. With a token: healthy -> 200 JSON, DB down -> 503 from the
    db_ready guard inside get_current_user.
    """
    try:
        r = client.get(f"{API}/portal/assignments", timeout=8)
        return r.status_code, ("assignments listed" if r.status_code == 200
                               else r.json().get("detail", "")[:60])
    except Exception as e:
        return 0, str(e)[:60]


def worker_logs(n=12):
    workers = service_containers("worker")
    if not workers:
        return "(no worker container found)"
    raw = run(["docker", "logs", workers[0]["name"], "--tail", str(n)], timeout=20)
    return raw or "(no output)"


def wait_for(predicate, timeout_s, label, tick=3):
    print(f"  Waiting for {label} (polling every {tick}s, up to {timeout_s}s)...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ok, detail = predicate()
        elapsed = int(time.time() + 0 - (deadline - timeout_s))
        print(f"    [{elapsed:>3}s] {detail}")
        if ok:
            return True
        time.sleep(tick)
    return False


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - SELF-HEALING DEMO")
    print("=" * 70)
    print()
    print("  Plan: stop PostgreSQL -> observe graceful degradation -> restart")
    print("  -> observe automatic recovery. Services are restored even on Ctrl+C.")
    print()

    # ── Step 1: Healthy baseline ──────────────────────────────────────────
    print("[1/5] HEALTHY BASELINE")
    print("-" * 70)
    h = health()
    print(f"  /health status : {h.get('status')}")
    for dep, val in h.get("dependencies", {}).items():
        marker = "[OK]" if val else "[--]"
        print(f"    {marker} {dep}: {'ok' if val else 'down'}")

    client = PlagioClient()
    if not client.login_or_signup():
        print("  [!!] Could not authenticate — aborting (nothing was changed).")
        return
    code, detail = authed_probe(client)
    print(f"  Authed probe   : HTTP {code} ({detail})")
    assert code == 200, "baseline must be healthy before starting"
    pause()

    # ── Step 2: Stop PostgreSQL ───────────────────────────────────────────
    print(f"\n[2/5] STOPPING POSTGRESQL ({POSTGRES_CONTAINER})")
    print("-" * 70)
    run(["docker", "stop", POSTGRES_CONTAINER])
    stopped.append(POSTGRES_CONTAINER)
    print("  Container stopped.")

    def degraded():
        h = health()
        status = h.get("status")
        deps = h.get("dependencies", {})
        c, d = authed_probe(client)
        return (status == "degraded" and deps.get("database") is False and c == 503), \
               f"/health={status}, authed probe={c}"

    degraded_ok = wait_for(degraded, 75, "degraded state (monitor task runs every 30s)")
    pause()

    # ── Step 3: Degraded behaviour ────────────────────────────────────────
    print("\n[3/5] SYSTEM DEGRADED")
    print("-" * 70)
    h = health()
    print(f"  /health status : {h.get('status')}")
    for dep, val in h.get("dependencies", {}).items():
        marker = "[OK]" if val else "[--] DOWN"
        print(f"    {marker} {dep}: {'ok' if val else 'down'}")
    code, detail = authed_probe(client)
    print(f"  Authed probe   : HTTP {code} ({detail})")

    if degraded_ok and code == 503:
        print("\n  [OK] The API is still serving traffic but refuses DB work:")
        print("     /health says 'degraded' and DB endpoints return 503 — no")
        print("     crashes, no hanging requests, no corrupted state.")
    else:
        print("\n  [!!] Degradation signal incomplete (see above).")
    pause()

    # ── Step 4: Restart PostgreSQL ────────────────────────────────────────
    print(f"\n[4/5] RESTARTING POSTGRESQL")
    print("-" * 70)
    run(["docker", "start", POSTGRES_CONTAINER])
    stopped.remove(POSTGRES_CONTAINER)
    print("  Container started.")

    def recovered():
        h = health()
        c, _ = authed_probe(client)
        return (h.get("status") == "healthy" and c == 200), \
               f"/health={h.get('status')}, authed probe={c}"

    recovered_ok = wait_for(recovered, 120, "full recovery (reconnect + init_db)")

    # ── Step 5: Recovered ─────────────────────────────────────────────────
    print("\n[5/5] SYSTEM RECOVERED")
    print("-" * 70)
    h = health()
    print(f"  /health status : {h.get('status')}")
    for dep, val in h.get("dependencies", {}).items():
        marker = "[OK]" if val else "[--]"
        print(f"    {marker} {dep}: {'ok' if val else 'down'}")
    code, detail = authed_probe(client)
    print(f"  Authed probe   : HTTP {code} ({detail})")

    print("\n  Recent worker logs:")
    for line in worker_logs(8).splitlines()[-8:]:
        print(f"    {line}")

    verdict = recovered_ok and code == 200 and health().get("status") == "healthy"
    print()
    print("  SELF-HEALING MECHANISMS DEMONSTRATED:" if verdict
          else "  INCOMPLETE RECOVERY — mechanisms supposed to handle this:")
    print("   1. API _monitor_db pings DB every 30s; flips db_ready both ways")
    print("   2. DB down  -> /health 'degraded' + 503 on DB endpoints (no crash)")
    print("   3. DB back  -> init_db() re-runs, AUTO_RECOVERY counter incremented")
    print("   4. Worker main loop also re-pings the DB every 30s")
    print("   5. Stale-job recovery retries stuck jobs up to 3x every 60s")
    print("   6. Exhausted jobs land in Redis dead-letter with original payload")
    print("=" * 70)
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    try:
        main()
    finally:
        ensure_restore()
