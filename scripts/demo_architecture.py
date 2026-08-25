#!/usr/bin/env python3
"""
Demo Script 1: Microservices Architecture
Shows all containers, their roles, ports, and resource limits.
Run: python scripts/demo_architecture.py
"""

import json
import subprocess
import sys


def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()


def get_containers():
    raw = run(
        'docker ps --format '
        '{"name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}"}'
    )
    containers = []
    for line in raw.splitlines():
        if line.strip():
            containers.append(json.loads(line))
    return containers


def get_inspect(name):
    raw = run(f'docker inspect {name}')
    data = json.loads(raw)
    if not data:
        return {}
    c = data[0]
    hc = c.get("Config", {}).get("Healthcheck", {})
    host = c.get("HostConfig", {})
    return {
        "cpu": host.get("NanoCpus", 0) / 1e9 if host.get("NanoCpus") else host.get("CpuPeriod", 0),
        "memory_mb": (host.get("Memory", 0) or 0) / (1024 * 1024),
        "restart": host.get("RestartPolicy", {}).get("Name", "no"),
        "health_cmd": " + ".join(hc.get("Test", [""])[-1:]) if hc else "none",
    }


ROLES = {
    "plagioscale-api-service": ("API Server", "FastAPI REST API — handles auth, submissions, assignments, CSRF, JWT", "8000"),
    "plagioscale-worker": ("Worker", "Background job processor — runs similarity + AI detection", "8001"),
    "plagioscale-autoscaler": ("Autoscaler", "Watches Redis queue depth, scales workers 1–5 via Docker SDK", "8002"),
    "plagioscale-monitoring": ("Monitoring", "Live dashboard — queue length, workers, job status, health grid", "8090"),
    "plagioscale-postgres": ("PostgreSQL", "Primary database — users, assignments, submissions, jobs", "5432"),
    "plagioscale-redis": ("Redis", "Job queue + caching — enqueues jobs, stores results, autoscaler events", "6379"),
    "plagioscale-prometheus": ("Prometheus", "Metrics scraping — scrapes 4 services every 5s, 5 alert rules", "9090"),
    "plagioscale-grafana": ("Grafana", "Metrics dashboards — 2 pre-provisioned dashboards with live graphs", "3000"),
    "plagioscale-alertmanager": ("Alertmanager", "Alert routing — receives Prometheus alerts, forwards to API webhook", "9093"),
    "plagioscale-frontend": ("Frontend", "React + Vite — SPA served via Nginx on port 80", "3050"),
    "plagioscale-portainer": ("Portainer", "Docker management UI — container lifecycle management", "9000"),
}


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def main():
    print("=" * 70)
    print("  PLAGIOSCALE — MICROSERVICES ARCHITECTURE DEMO")
    print("=" * 70)

    # --- Section 1: Container Overview ---
    print("\n[1/3] RUNNING CONTAINERS")
    print("-" * 70)
    containers = get_containers()
    print(f"  {'Container':<30} {'Status':<25} {'Ports'}")
    print(f"  {'─' * 30} {'─' * 25} {'─' * 30}")
    for c in sorted(containers, key=lambda x: x["name"]):
        short = c["name"].replace("plagioscale-", "")
        print(f"  {short:<30} {c['status']:<25} {c['ports'][:40]}")
    print(f"\n  Total: {len(containers)} containers running")

    pause()

    # --- Section 2: Resource Limits ---
    print("\n[2/3] RESOURCE LIMITS PER CONTAINER")
    print("-" * 70)
    print(f"  {'Container':<25} {'CPU':>8} {'Memory':>10} {'Restart':<15}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 10} {'─' * 15}")
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
        print(f"  {short:<25} {cpu:>5.2f}   {mem:>7.0f}MB   {restart}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 10}")
    print(f"  {'TOTAL':<25} {total_cpu:>5.2f}   {total_mem:>7.0f}MB")

    pause()

    # --- Section 3: Roles ---
    print("\n[3/3] MICROSERVICE ROLES")
    print("-" * 70)
    for name, (title, desc, port) in sorted(ROLES.items()):
        running = any(name in c["name"] for c in containers)
        status = "✓" if running else "✗"
        print(f"\n  {status} {title} (:{port})")
        print(f"    {desc}")

    print("\n" + "=" * 70)
    print("  KEY ARCHITECTURE POINTS:")
    print("  • Each service runs in its own container with isolated resources")
    print("  • Worker processes jobs from Redis queue — independent of API")
    print("  • Autoscaler monitors queue depth, creates/destroys workers via Docker socket")
    print("  • Prometheus scrapes metrics from 4 services; Grafana visualizes them")
    print("  • Alertmanager routes critical alerts to API webhook for auto-remediation")
    print("=" * 70)


if __name__ == "__main__":
    main()
