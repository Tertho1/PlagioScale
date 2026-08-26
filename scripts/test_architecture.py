#!/usr/bin/env python3
"""
Demo Script 1: Microservices Architecture
Lists all PlagioScale containers (compose-label filtered), their health,
resource limits and roles — then probes each service's HTTP surface to prove
the architecture is wired correctly.
Run: python scripts/test_architecture.py
"""

import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, FRONTEND, MONITORING, PROJECT, pause, run, service_containers, short


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
        "health_interval": hc.get("Interval", 0) // 1_000_000_000 if hc else None,
        "health_cmd": (hc.get("Test", [""])[-1] if hc.get("Test") else None),
    }


ROLES = {
    "api-service": ("API Server", "FastAPI REST API - auth, submissions, CSRF, JWT, metrics", ":8000"),
    "worker": ("Worker", "Background processor - hybrid similarity + AI detection (scales 1-5)", ":8001"),
    "autoscaler": ("Autoscaler", "Watches queue depth + API load; clones/stops containers via Docker SDK", ":8002"),
    "monitoring-service": ("Monitoring", "Live dashboard - queue, workers, jobs, container health grid", ":8090"),
    "postgres": ("PostgreSQL", "Primary database - users, assignments, submissions, results", ":5432"),
    "redis": ("Redis", "Job queue + cache - LPUSH/BRPOP pipeline, autoscaler events", ":6379"),
    "prometheus": ("Prometheus", "Metrics store - scrapes all services every 5s + alert rules", ":9090"),
    "grafana": ("Grafana", "Dashboards - pre-provisioned overview + audit boards", ":3000"),
    "alertmanager": ("Alertmanager", "Alert routing - forwards firing alerts to API webhook", ":9093"),
    "frontend": ("Frontend", "React SPA via Nginx :3050 - reverse-proxies /api to API replicas", ":3050"),
}

# service -> (label, url, expectation)
PROBES = [
    ("frontend", f"{FRONTEND}", 200),
    ("api (via nginx /api proxy)", f"{API}/health", 200),
    ("monitoring dashboard", f"{MONITORING}/api/overview", 200),
    ("autoscaler metrics", "http://localhost:8002/metrics", 200),
    ("prometheus", "http://localhost:9090/-/healthy", 200),
    ("grafana", "http://localhost:3000/api/health", 200),
    ("alertmanager", "http://localhost:9093/-/healthy", 200),
]


def main():
    print("=" * 70)
    print(f"  PLAGIOSCALE - MICROSERVICES ARCHITECTURE DEMO  (project: {PROJECT})")
    print("=" * 70)

    # --- Section 1: Container Overview ---
    print("\n[1/4] RUNNING CONTAINERS (health from Docker)")
    print("-" * 70)
    services = ["api-service", "worker", "autoscaler", "monitoring-service",
                "postgres", "redis", "prometheus", "grafana", "alertmanager", "frontend"]
    found = {}
    for svc in services:
        found[svc] = service_containers(svc)

    print(f"  {'Container':<28} {'Status':<30}")
    print(f"  {'-' * 28} {'-' * 30}")
    total = 0
    for svc in services:
        for c in found[svc]:
            total += 1
            print(f"  {short(c['name']):<28} {c['status']:<30}")
    print(f"\n  Total: {total} containers")
    pause()

    # --- Section 2: Resource Limits ---
    print("\n[2/4] RESOURCE LIMITS PER CONTAINER (enforced by Docker cgroups)")
    print("-" * 70)
    print(f"  {'Container':<26} {'CPU':>5} {'Memory':>8} {'Restart':<15} {'Health':>7}")
    print(f"  {'-' * 26} {'-' * 5} {'-' * 8} {'-' * 15} {'-' * 7}")
    total_cpu, total_mem = 0.0, 0
    for svc in services:
        for c in found[svc]:
            info = get_inspect(c["name"])
            cpu = info["cpu"]
            mem = info["memory_mb"]
            total_cpu += cpu or 0
            total_mem += mem
            healthy = "(healthy)" in c["status"]
            print(f"  {short(c['name']):<26} "
                  f"{(f'{cpu:.2f}' if cpu is not None else 'n/a'):>5} "
                  f"{mem:>6}MB   {info['restart']:<15} {'yes' if healthy else 'n/a':>7}")
    print(f"  {'-' * 26} {'-' * 5} {'-' * 8}")
    print(f"  {'TOTAL':<26} {total_cpu:>5.2f} {total_mem:>6}MB")
    pause()

    # --- Section 3: Live connectivity probes ---
    print("\n[3/4] LIVE SERVICE PROBES (proving the wiring works)")
    print("-" * 70)
    for label, url_, expected in PROBES:
        try:
            r = requests.get(url_, timeout=5)
            ok = r.status_code == expected
            marker = "[OK]" if ok else "[!!]"
            extra = "" if ok else f" (got {r.status_code})"
            print(f"  {marker} {label:<32} {url_}{extra}")
        except Exception as e:
            print(f"  [--] {label:<32} {url_} ({str(e)[:40]})")

    ov = {}
    try:
        ov = requests.get(f"{MONITORING}/api/overview", timeout=5).json()
        print(f"\n  Monitoring sees: queue={ov.get('queue_length')}  "
              f"workers={ov.get('workers')}  api_replicas={ov.get('api_replicas')}  "
              f"jobs={ov.get('jobs')}")
    except Exception:
        pass
    pause()

    # --- Section 4: Roles ---
    print("\n[4/4] MICROSERVICE ROLES")
    print("-" * 70)
    for svc, (title, desc, port) in sorted(ROLES.items(), key=lambda kv: kv[1][2]):
        running = bool(found.get(svc))
        status = "[OK]" if running else "[--]"
        print(f"\n  {status} {title} ({port})")
        print(f"     {desc}")

    print("\n" + "=" * 70)
    print("  KEY ARCHITECTURE POINTS:")
    print("  * Each service runs in its own container with isolated resources")
    print("  * Worker pulls jobs from the Redis queue - fully decoupled from API")
    print("  * Autoscaler scales workers by queue depth AND API replicas by active requests")
    print("  * Frontend Nginx resolves api-service via Docker DNS -> round-robin replicas")
    print("  * Prometheus scrapes every service; Grafana visualizes; alerts hit the API webhook")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
