#!/usr/bin/env python3
"""
Demo Script 5: Resource Isolation
Shows CPU, memory, health checks, and restart policies on each container.
Run: python scripts/demo_resources.py
"""

import json
import os
import subprocess
import sys

COMPOSE_FILE = "docker-compose.yml"


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def run(cmd):
    with os.popen(cmd) as f:
        return f.read().strip()


def get_containers():
    raw = run('docker ps --format "{{.Names}}~{{.Image}}~{{.Status}}"')
    containers = []
    for line in raw.splitlines():
        if line.strip():
            parts = line.split("~")
            if len(parts) >= 3:
                containers.append({"name": parts[0], "image": parts[1], "status": parts[2]})
    return containers


def get_inspect(name):
    raw = run(f"docker inspect {name}")
    data = json.loads(raw)
    if not data:
        return {}
    c = data[0]
    host = c.get("HostConfig", {})
    hc = c.get("Config", {}).get("Healthcheck", {})
    return {
        "cpu": host.get("NanoCpus", 0) / 1e9 if host.get("NanoCpus") else 0,
        "memory_mb": (host.get("Memory", 0) or 0) / (1024 * 1024),
        "restart": host.get("RestartPolicy", {}).get("Name", "no"),
        "max_restarts": host.get("RestartPolicy", {}).get("MaximumRetryCount", 0),
        "health_cmd": (hc.get("Test", [""])[-1] if hc.get("Test") else "none"),
        "health_interval": hc.get("Interval", 0) // 1_000_000_000,  # ns -> s
        "image": c.get("Config", {}).get("Image", "?"),
    }


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - RESOURCE ISOLATION DEMO")
    print("=" * 70)

    # --- Step 1: Resource Table ---
    print("\n[1/3] RESOURCE LIMITS PER CONTAINER")
    print("-" * 70)
    containers = get_containers()
    print(f"  {'Container':<22} {'CPU':>6} {'Memory':>8} {'Restart':<15}")
    print(f"  {'-' * 22} {'-' * 6} {'-' * 8} {'-' * 15}")
    total_cpu = 0.0
    total_mem = 0.0
    for c in sorted(containers, key=lambda x: x["name"]):
        short = c["name"].replace("plagioscale-", "")
        info = get_inspect(c["name"])
        cpu = info.get("cpu", 0)
        mem = info.get("memory_mb", 0)
        restart = info.get("restart", "no")
        total_cpu += cpu
        total_mem += mem
        print(f"  {short:<22} {cpu:>4.2f}   {mem:>5.0f}MB   {restart}")
    print(f"  {'-' * 22} {'-' * 6} {'-' * 8}")
    print(f"  {'TOTAL':<22} {total_cpu:>4.2f}   {total_mem:>5.0f}MB")
    pause()

    # --- Step 2: Health Checks ---
    print("\n[2/3] HEALTH CHECK CONFIGURATION")
    print("-" * 70)
    print(f"  {'Container':<22} {'Interval':<10} {'Command'}")
    print(f"  {'-' * 22} {'-' * 10} {'-' * 40}")
    for c in sorted(containers, key=lambda x: x["name"]):
        short = c["name"].replace("plagioscale-", "")
        info = get_inspect(c["name"])
        interval = info.get("health_interval", 0)
        cmd = info.get("health_cmd", "none")
        if len(cmd) > 40:
            cmd = cmd[:37] + "..."
        print(f"  {short:<22} {interval:>6}s   {cmd}")
    print()
    print("  Health checks ensure Docker monitors each container.")
    print("  If a check fails, Docker marks the container as 'unhealthy'.")
    print("  The monitoring dashboard shows real-time health status.")
    pause()

    # --- Step 3: Isolation Explanation ---
    print("\n[3/3] RESOURCE ISOLATION EXPLAINED")
    print("-" * 70)
    print()
    print("  WHY THIS MATTERS:")
    print("  Without limits, one container can consume ALL host resources,")
    print("  starving others. This makes autoscaling unrealistic.")
    print()
    print("  YOUR CLUSTER ALLOCATION:")
    print(f"    Total CPU:    {total_cpu:.1f} cores")
    print(f"    Total Memory: {total_mem:.0f} MB")
    print()
    print("  KEY ISOLATION POINTS:")
    print("  * Worker gets 2GB RAM - enough for ML models (SBERT + RoBERTa + GPT2)")
    print("  * API gets 0.5 CPU - sufficient for request handling")
    print("  * Autoscaler gets only 0.1 CPU - lightweight monitoring")
    print("  * No container can exceed its allocation")
    print("  * Restart policy: all set to 'unless-stopped' (auto-restart on crash)")
    print()
    print("  DEMONSTRATION:")
    print("  Try running a memory-heavy process inside a container:")
    print("    docker exec plagioscale-worker-1 python -c 'x = bytearray(3*1024*1024*1024)'")
    print("  -> Will be killed by Docker OOM killer (memory limit enforced)")
    print()
    print("=" * 70)
    print("  SUMMARY:")
    print("  * 11 containers, each with CPU + memory limits")
    print("  * All have health checks (Docker monitors liveness)")
    print("  * All auto-restart on failure (unless-stopped)")
    print("  * Resource isolation prevents cascading failures")
    print("  * Autoscaler respects limits when creating new workers")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        pause("\nPress Enter to exit...")
