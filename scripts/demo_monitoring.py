#!/usr/bin/env python3
"""
Demo Script 4: Monitoring Stack
Shows Prometheus targets, alerts, Grafana dashboards, monitoring service.
Run: python scripts/demo_monitoring.py
"""

import json
import subprocess
import sys
import time

import requests

PROMETHEUS = "http://localhost:9090"
GRAFANA = "http://localhost:3000"
MONITORING = "http://localhost:8090"


def pause(msg="\nPress Enter to continue..."):
    input(msg)


def prom_query(path):
    try:
        r = requests.get(f"{PROMETHEUS}{path}", timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def main():
    print("=" * 70)
    print("  PLAGIOSCALE — MONITORING STACK DEMO")
    print("=" * 70)

    # --- Step 1: Prometheus Targets ---
    print("\n[1/5] PROMETHEUS — SCRAPE TARGETS")
    print("-" * 70)
    data = prom_query("/api/v1/targets")
    if data and data.get("status") == "success":
        targets = data["data"]["activeTargets"]
        print(f"  {'Job':<25} {'Endpoint':<35} {'State':<10}")
        print(f"  {'─' * 25} {'─' * 35} {'─' * 10}")
        for t in targets:
            job = t.get("labels", {}).get("job", "?")
            ep = t.get("scrapeUrl", "?")
            state = t.get("health", "?")
            marker = "✓" if state == "up" else "✗"
            print(f"  {job:<25} {ep:<35} {marker} {state}")
        print(f"\n  Total: {len(targets)} targets, "
              f"{sum(1 for t in targets if t.get('health') == 'up')} UP")
    else:
        print("  ✗ Cannot reach Prometheus")
    pause()

    # --- Step 2: Prometheus Alerts ---
    print("\n[2/5] PROMETHEUS — ALERT RULES")
    print("-" * 70)
    data = prom_query("/api/v1/rules")
    if data and data.get("status") == "success":
        rules = data["data"]["groups"]
        alert_count = 0
        for group in rules:
            for rule in group.get("rules", []):
                if rule.get("type") == "alerting":
                    alert_count += 1
                    name = rule.get("name", "?")
                    severity = rule.get("labels", {}).get("severity", "?")
                    state = rule.get("state", "?")
                    expr = rule.get("query", "?")[:60]
                    print(f"  {alert_count}. {name}")
                    print(f"     Severity: {severity} | State: {state}")
                    print(f"     Expr: {expr}...")
                    print()
        print(f"  Total: {alert_count} alert rules defined")
    else:
        print("  ✗ Cannot reach Prometheus")
    pause()

    # --- Step 3: Monitoring Service ---
    print("\n[3/5] MONITORING SERVICE — LIVE DASHBOARD")
    print("-" * 70)
    try:
        r = requests.get(f"{MONITORING}/api/overview", timeout=5)
        if r.status_code == 200:
            overview = r.json()
            print(f"  Queue length:     {overview.get('queue_length', '?')}")
            print(f"  Workers running:  {overview.get('workers', '?')}")
            jobs = overview.get("jobs", {})
            print(f"  Jobs completed:   {jobs.get('completed', '?')}")
            print(f"  Jobs processing:  {jobs.get('processing', '?')}")
            print(f"  Jobs failed:      {jobs.get('failed', '?')}")
        else:
            print(f"  ✗ Status: {r.status_code}")
    except Exception as e:
        print(f"  ✗ Cannot reach monitoring service: {e}")

    print()
    try:
        r = requests.get(f"{MONITORING}/api/health-summary", timeout=5)
        if r.status_code == 200:
            containers = r.json().get("containers", [])
            print("  Container Health Grid:")
            for c in containers:
                name = c.get("name", "?").replace("plagioscale-", "")
                status = c.get("status", "?")
                health = c.get("health", "")
                marker = "✓" if "healthy" in str(status).lower() or "running" in str(status).lower() else "?"
                print(f"    {marker} {name:<25} {status} {health}")
    except Exception:
        pass
    pause()

    # --- Step 4: Grafana Dashboards ---
    print("\n[4/5] GRAFANA — PRE-PROVISIONED DASHBOARDS")
    print("-" * 70)
    print("  Dashboards available at: http://localhost:3000 (admin/admin)")
    print()
    print("  1. PlagioScale Overview")
    print("     URL: http://localhost:3000/d/plagioscale-overview")
    print("     Panels: Queue Length, Workers, Job Throughput, Scale Events")
    print()
    print("  2. Audit & Operations")
    print("     URL: http://localhost:3000/d/plagioscale-audit")
    print("     Panels: Requests/min, Queue Length, Workers, Job Throughput")
    print()
    print("  Datasource: Prometheus (http://prometheus:9090)")
    print("  Auto-refresh: 10s")

    # Try to list dashboards via Grafana API
    try:
        r = requests.get(f"{GRAFANA}/api/search", timeout=5,
                         auth=("admin", "admin"))
        if r.status_code == 200:
            dashboards = r.json()
            print(f"\n  Grafana reports {len(dashboards)} dashboard(s):")
            for d in dashboards:
                print(f"    - {d.get('title', '?')} (uid: {d.get('uid', '?')})")
    except Exception:
        pass
    pause()

    # --- Step 5: Alertmanager ---
    print("\n[5/5] ALERTMANAGER — ALERT ROUTING")
    print("-" * 70)
    try:
        r = requests.get("http://localhost:9093/api/v2/status", timeout=5)
        if r.status_code == 200:
            print("  Alertmanager is running")
        else:
            print(f"  Status: {r.status_code}")
    except Exception:
        print("  ✗ Cannot reach Alertmanager")

    print()
    print("  Alert Flow:")
    print("  Prometheus ──scrape──▶ 4 services (api, worker, autoscaler, monitoring)")
    print("       │")
    print("       ▼")
    print("  5 alert rules (ServiceDown, QueueDepthHigh, JobFailureRate, etc.)")
    print("       │")
    print("       ▼")
    print("  Alertmanager ──webhook──▶ API /api/webhooks/alertmanager")
    print("       │")
    print("       ▼")
    print("  Auto-remediation (rate-limit counters, audit logging)")
    print()
    print("=" * 70)
    print("  MONITORING STACK SUMMARY:")
    print("  • Prometheus: scrapes 4 targets, 5s interval, 5 alert rules")
    print("  • Grafana: 2 dashboards, auto-refresh, Prometheus datasource")
    print("  • Monitoring: live HTML dashboard, health grid, autoscaler events")
    print("  • Alertmanager: routes alerts to API webhook for auto-remediation")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        pause("\nPress Enter to exit...")
