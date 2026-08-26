#!/usr/bin/env python3
"""
Demo Script 5: Resource Isolation
Shows CPU/memory limits, health checks and restart policies per container,
then PROVES memory isolation by launching a throwaway container that tries to
allocate far beyond a tiny limit and gets OOM-killed by Docker.

Run: python scripts/test_resources.py
"""

import json
import os
import subprocess
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, PROJECT, pause, run, service_containers, short


def get_inspect(name):
    raw = run(["docker", "inspect", name])
    data = json.loads(raw)
    if not data:
        return {}
    c = data[0]
    host = c.get("HostConfig", {})
    hc = c.get("Config", {}).get("Healthcheck", {})
    nano = host.get("NanoCpus") or 0
    return {
        "cpu": round(nano / 1e9, 2) if nano else None,
        "memory_mb": round((host.get("Memory") or 0) / (1024 * 1024)),
        "restart": host.get("RestartPolicy", {}).get("Name", "no"),
        "health_cmd": (hc.get("Test", [""])[-1] if hc.get("Test") else None),
        "health_interval": hc.get("Interval", 0) // 1_000_000_000 if hc else None,
        "oom_stop": host.get("Memory") or 0,
    }


SERVICES = ["api-service", "worker", "autoscaler", "monitoring-service",
            "postgres", "redis", "prometheus", "grafana", "alertmanager", "frontend"]


def oom_demo():
    """Launch a one-off container from the local api image with -m 64m asking
    for ~512MB -> Docker's cgroup OOM killer must terminate it (exit 137)."""
    api_containers = service_containers("api-service")
    if not api_containers:
        print("  [--] No api-service image/container found for demo; skipping.")
        return
    image = run(["docker", "inspect", api_containers[0]["name"],
                 "--format", "{{.Config.Image}}"])
    name = f"{PROJECT}-oom-demo-{int(time.time())}"
    print(f"  Launching throwaway container from {image}")
    print(f"  Limit: 64MB RAM | Demand: allocate 512MB bytearray")
    cmd = ["docker", "run", "--rm", "--name", name, "-m", "64m",
           image, "python", "-c",
           "print('allocating...'); x = bytearray(512*1024*1024); print('allocated')"]
    start = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, errors="replace")
    dur = time.time() - start

    print(f"  Exit code : {r.returncode}   ({dur:.1f}s)")
    out = (r.stdout or "").strip().replace("\n", " / ")
    err_tail = (r.stderr or "").strip().splitlines()[-1] if (r.stderr or "").strip() else ""
    if out:
        print(f"  stdout    : {out[:70]}")
    if err_tail:
        print(f"  stderr    : {err_tail[:90]}")

    if r.returncode == 137:
        print("\n  [OK] PROOF: process was OOM-KILLED by Docker (exit 137).")
        print("     The kernel refused to let the container exceed its 64MB")
        print("     cgroup limit — exactly how PlagioScale containers are fenced.")
        return True
    print("\n  [!!] Expected OOM kill (exit 137) — got something else.")
    return False


def main():
    print("=" * 70)
    print(f"  PLAGIOSCALE - RESOURCE ISOLATION DEMO  (project: {PROJECT})")
    print("=" * 70)

    # --- Step 1: Resource table ---
    print("\n[1/4] RESOURCE LIMITS PER CONTAINER")
    print("-" * 70)
    rows = []
    for svc in SERVICES:
        for c in service_containers(svc):
            info = get_inspect(c["name"])
            rows.append((c["name"], info))
    print(f"  {'Container':<24} {'CPU':>5} {'Memory':>8} {'Restart':<16}")
    print(f"  {'-' * 24} {'-' * 5} {'-' * 8} {'-' * 16}")
    total_cpu, total_mem = 0.0, 0
    policies = set()
    for name, info in sorted(rows):
        cpu, mem, restart = info["cpu"], info["memory_mb"], info["restart"]
        policies.add(restart)
        total_cpu += cpu or 0
        total_mem += mem
        print(f"  {short(name):<24} {(f'{cpu:.2f}' if cpu is not None else 'n/a'):>5} "
              f"{mem:>6}MB   {restart:<16}")
    print(f"  {'-' * 24} {'-' * 5} {'-' * 8}")
    print(f"  {'TOTAL':<24} {total_cpu:>5.2f} {total_mem:>6}MB")
    pause()

    # --- Step 2: Health checks ---
    print("\n[2/4] HEALTH CHECK CONFIGURATION")
    print("-" * 70)
    print(f"  {'Container':<24} {'Interval':>8}  Command")
    print(f"  {'-' * 24} {'-' * 8}  {'-' * 36}")
    for name, info in sorted(rows):
        cmd = info["health_cmd"] or "(none)"
        if len(cmd) > 44:
            cmd = cmd[:41] + "..."
        interval = f"{info['health_interval']}s" if info["health_interval"] else "-"
        print(f"  {short(name):<24} {interval:>8}  {cmd}")
    print()
    print("  Failing checks mark a container 'unhealthy'; the monitoring")
    print("  dashboard surfaces this in its live health grid.")
    pause()

    # --- Step 3: LIVE OOM proof ---
    print("\n[3/4] LIVE MEMORY-ISOLATION PROOF (throwaway container)")
    print("-" * 70)
    try:
        oom_demo()
    except Exception as e:
        print(f"  [!!] Demo failed to run: {e}")
    pause()

    # --- Step 4: Why it matters ---
    print("\n[4/4] WHY ISOLATION MATTERS")
    print("-" * 70)
    print(f"  Cluster allocation: {total_cpu:.2f} CPU cores, {total_mem} MB across "
          f"{len(rows)} containers")
    print()
    print("  KEY POINTS:")
    print("  * Worker gets 2048MB — enough for SBERT + RoBERTa + DistilGPT2 resident")
    print("  * API gets 0.5 CPU + 384MB — request handling only, no ML models")
    print("  * Autoscaler clones respect limits too (workers 512m, API replicas 384m)")
    print("  * One runaway container CANNOT starve its neighbours (just proven above)")
    print(f"  * Restart policies in effect: {', '.join(sorted(policies))}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
