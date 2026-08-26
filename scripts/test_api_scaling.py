#!/usr/bin/env python3
"""
API Auto-Scaling Demo
Generates sustained HTTP load through the frontend proxy and shows — live —
how the autoscaler watches ACTIVE REQUESTS per replica and clones api-service
containers when the count exceeds its threshold (1 -> N), then removes them
again once load drops (N -> 1).

You will see a continuous table where every row is one observation:
  Time | Fleet active requests (marked !UP / !DOWN vs thresholds) | Replicas
plus a per-replica breakdown (active/served) and the autoscaler's own decision
lines printed inline, e.g.  >>> autoscaler: Scaled API to 2 replicas

Run: python scripts/test_api_scaling.py
"""

import os
import sys
import threading
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (API, PlagioClient, autoscaler_events, container_http_json,
                    pause, service_containers, short)

SCALE_UP_THRESHOLD = int(os.getenv("API_SCALE_UP_THRESHOLD", "20"))   # matches compose
SCALE_DOWN_THRESHOLD = int(os.getenv("API_SCALE_DOWN_THRESHOLD", "5"))
MAX_API = int(os.getenv("MAX_API", "5"))                              # compose cap
TARGET_REPLICAS = min(int(os.getenv("DEMO_TARGET_REPLICAS", "3")), MAX_API)
NUM_THREADS = int(os.getenv("DEMO_THREADS", "80"))

# Any running container on the compose network can reach the API replicas;
# use the first one we can exec into as a relay host (container IPs are not
# routable from the Windows host).
def _relay_container():
    for svc in ("autoscaler", "monitoring-service"):
        cs = service_containers(svc)
        if cs:
            return cs[0]["name"]
    return None


RELAY = _relay_container()


def fleet_metrics():
    """[{name, active, total, ok}] for every running API replica."""
    out = []
    for c in service_containers("api-service"):
        data = None
        if RELAY and c["ip"]:
            data = container_http_json(RELAY, f"http://{c['ip']}:8000/metrics")
        if isinstance(data, dict):
            out.append({"name": c["name"], "active": data.get("active_requests", 0),
                        "total": data.get("request_count"), "ok": True})
        else:
            out.append({"name": c["name"], "active": 0, "total": None, "ok": False})
    return out


def fmt_extra(e):
    extra = {k: v for k, v in e.items() if k not in ("timestamp", "level", "message")}
    return f" {{{', '.join(f'{k}={v}' for k, v in extra.items())}}}" if extra else ""


def main():
    print("=" * 66)
    print("  API AUTO-SCALING DEMO — live request count drives replica count")
    print("=" * 66)

    client = PlagioClient()
    if not client.login_or_signup():
        return 1

    fleet = fleet_metrics()
    initial = len(fleet)
    print(f"\n  Autoscaler rule : active_requests > {SCALE_UP_THRESHOLD} -> +1 replica"
          f"   |   < {SCALE_DOWN_THRESHOLD} -> remove  (30s cooldown, cap {MAX_API})")
    print(f"  Load simulation : {NUM_THREADS} threads held until {TARGET_REPLICAS} "
          f"replicas are running")
    print(f"  Load generator  : -> {API}/health via nginx (100ms delay per request)")
    print(f"  API replicas    : {initial} {[short(f['name']) for f in fleet]}")
    pause()

    # ── Phase 1: start the load ───────────────────────────────────────────
    print(f"\n[1/2] STARTING LOAD ({NUM_THREADS} threads)")
    print("-" * 66)
    stop = threading.Event()
    sent = [0]
    errs = [0]
    local = threading.local()  # one pooled Session per thread: no TCP churn

    def get_session():
        if not hasattr(local, "s"):
            s = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=4)
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            local.s = s
        return local.s

    def load_worker():
        while not stop.is_set():
            try:
                get_session().get(f"{API}/health", timeout=10)
                sent[0] += 1
            except Exception:
                errs[0] += 1

    threads = [threading.Thread(target=load_worker, daemon=True) for _ in range(NUM_THREADS)]
    for t in threads:
        t.start()
    print("  Hammering /health — each in-flight request counts toward the threshold")

    # Remember existing events so only NEW autoscaler decisions get printed
    seen_events = {e.get("timestamp") for e in
                   autoscaler_events(limit=30, message_prefixes=("scaled",))}

    # ── Phase 2: single live table from load start to scale-down ─────────
    print("\n[2/2] LIVE — ACTIVE REQUESTS DRIVE THE AUTOSCALER")
    print("-" * 66)
    print(f"  {'Time':>5}  {'Active':>14}  {'Repl':>4}  Per-replica (active/served)")
    print(f"  {'-'*5}  {'-'*14}  {'-'*4}  {'-'*40}")

    start = time.time()
    peak_active, max_repl = 0, initial
    scaled_up = scaled_down = False
    load_running = True

    while time.time() - start < 480:  # 8-minute budget
        time.sleep(3)
        elapsed = int(time.time() - start)
        fleet = fleet_metrics()
        n = len(fleet)
        active = sum(f["active"] for f in fleet)
        served = sum(f["total"] or 0 for f in fleet)
        peak_active = max(peak_active, active)
        max_repl = max(max_repl, n)

        if load_running and active > SCALE_UP_THRESHOLD:
            zone = "!UP (>" + str(SCALE_UP_THRESHOLD) + ")"
        elif not load_running and n > initial:
            zone = "cooling "
        elif not load_running and active < SCALE_DOWN_THRESHOLD:
            zone = "!DOWN(<" + str(SCALE_DOWN_THRESHOLD) + ")"
        else:
            zone = "between"

        detail = "  ".join(
            f"{short(f['name'])}:{f['active']}/{f['total']}"
            for f in fleet)
        event = ""
        if n > initial and not scaled_up:
            scaled_up = True
            event = f"<-- REPLICAS {initial} -> {n}"

        print(f"  {elapsed:>4}s  {active:>6} {zone:<8} {n:>3}   {detail}  {event}")

        # Inline autoscaler decisions (API ones only)
        for e in reversed(autoscaler_events(limit=10, message_prefixes=("scaled api",))):
            ts = e.get("timestamp")
            if ts and ts not in seen_events:
                seen_events.add(ts)
                print(f"        {'':<14}  {'':>3}   >>> autoscaler: "
                      f"{e.get('message')}{fmt_extra(e)}")

        # Keep the load on until TARGET_REPLICAS are running — every extra
        # replica costs one 30s cooldown window of sustained !UP traffic.
        if load_running and scaled_up and n >= TARGET_REPLICAS:
            stop.set()
            for t in threads:
                t.join(timeout=5)
            load_running = False
            print(f"        {'':<14}  {'':>3}   ... target {TARGET_REPLICAS} replicas "
                  f"reached; stopping load")
        elif load_running and scaled_up and elapsed > 180:
            stop.set()
            for t in threads:
                t.join(timeout=5)
            load_running = False
            print(f"        {'':<14}  {'':>3}   ... target not reached within 180s; "
                  f"stopping load anyway")

        if scaled_up and not load_running and n <= initial:
            scaled_down = True
            print(f"        {'':<14}  {'':>3}   <-- BACK TO BASELINE ({n})")
            break

    stop.set()

    # ── Results ──────────────────────────────────────────────────────────
    events = autoscaler_events(limit=6, message_prefixes=("scaled api",))
    if events:
        print("\n  Autoscaler decisions this run:")
        for e in reversed(events):
            print(f"    [{str(e.get('timestamp'))[11:19]}] {e.get('message')}{fmt_extra(e)}")

    print("\n  RESULTS")
    print("-" * 66)
    print(f"  Initial replicas     : {initial}")
    print(f"  Target replicas      : {TARGET_REPLICAS} "
          f"(reached: {'YES' if max_repl >= TARGET_REPLICAS else 'NO'})")
    print(f"  Peak replicas        : {max_repl} (cap {MAX_API})")
    print(f"  Peak active requests : {peak_active}")
    print(f"  Requests sent        : {sent[0]} (errors: {errs[0]})")
    print(f"  Scale UP trigger     : active > {SCALE_UP_THRESHOLD} "
          f"-> {'YES' if scaled_up else 'NO'}")
    print(f"  Scale DOWN trigger   : back to baseline -> {'YES' if scaled_down else 'NO'}")
    return 0 if (scaled_up and scaled_down) else 1


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        code = 130
    finally:
        pause("\nPress Enter to exit...")
    sys.exit(code)
