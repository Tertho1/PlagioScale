#!/usr/bin/env python3
"""
Demo Script 4: Monitoring Stack
Prometheus targets + rules + LIVE metric queries, monitoring dashboard data,
Grafana dashboards, Alertmanager state, and an end-to-end webhook delivery
into the API's auto-remediation endpoint.
Run: python scripts/test_monitoring.py
"""

import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, pause

PROMETHEUS = "http://localhost:9090"
GRAFANA = "http://localhost:3000"
MONITORING = "http://localhost:8090"
ALERTMANAGER = "http://localhost:9093"


def prom(path):
    try:
        r = requests.get(f"{PROMETHEUS}{path}", timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def main():
    print("=" * 70)
    print("  PLAGIOSCALE - MONITORING STACK DEMO")
    print("=" * 70)

    # --- Step 1: Prometheus targets ---
    print("\n[1/6] PROMETHEUS - SCRAPE TARGETS")
    print("-" * 70)
    data = prom("/api/v1/targets")
    if data and data.get("status") == "success":
        targets = data["data"]["activeTargets"]
        print(f"  {'Job':<22} {'State':<8} {'Last scrape'}")
        print(f"  {'-' * 22} {'-' * 8} {'-' * 20}")
        for t in sorted(targets, key=lambda t: t.get("labels", {}).get("job", "")):
            job = t.get("labels", {}).get("job", "?")
            health = t.get("health", "?")
            last = str(t.get("lastScrape", ""))[11:19]
            marker = "[OK]" if health == "up" else "[--]"
            print(f"  {marker} {job:<19} {health:<8} {last}")
        up = sum(1 for t in targets if t.get("health") == "up")
        print(f"\n  Total: {len(targets)} targets, {up} UP")
    else:
        print("  [--] Cannot reach Prometheus on :9090")
    pause()

    # --- Step 2: Alert rules ---
    print("\n[2/6] PROMETHEUS - ALERT RULES")
    print("-" * 70)
    data = prom("/api/v1/rules")
    if data and data.get("status") == "success":
        groups = data["data"]["groups"]
        n = 0
        firing = []
        for group in groups:
            for rule in group.get("rules", []):
                if rule.get("type") != "alerting":
                    continue
                n += 1
                name = rule.get("name", "?")
                severity = rule.get("labels", {}).get("severity", "?")
                state = rule.get("state", "?")
                if state == "firing":
                    firing.append(name)
                print(f"  {n:>2}. {name}")
                print(f"      severity={severity}  state={state}")
                print(f"      expr: {rule.get('query', '?')[:64]}")
        print(f"\n  Total: {n} alert rules; currently firing: {firing or 'none'}")
    else:
        print("  [--] Cannot reach Prometheus rules API")
    pause()

    # --- Step 3: LIVE metric queries (proves the pipeline end to end) ---
    print("\n[3/6] PROMETHEUS - LIVE METRIC QUERIES")
    print("-" * 70)
    queries = [
        ("plagioscale_queue_length", "Redis job queue depth"),
        ("plagioscale_workers", "running worker containers"),
        ("plagioscale_api_replicas", "API replica count"),
        ("plagioscale_api_active_requests", "in-flight API requests"),
        ("plagioscale_db_ready", "API database connection flag"),
    ]
    ok_any = False
    for query, desc in queries:
        data = prom(f"/api/v1/query?query={query}")
        results = (data or {}).get("data", {}).get("result", [])
        if results:
            value = results[0]["value"][1]
            ts_ok = bool(results[0]["value"][0])
            ok_any = ok_any or ts_ok
            print(f"  [OK] {query:<34} = {value:<8} ({desc})")
        else:
            print(f"  [--] {query:<34} = no data   ({desc})")
    if ok_any:
        print("\n  Metrics flow: service -> /metrics -> Prometheus -> queryable. Verified.")
    pause()

    # --- Step 4: Monitoring service ---
    print("\n[4/6] MONITORING SERVICE - LIVE DASHBOARD DATA")
    print("-" * 70)
    try:
        ov = requests.get(f"{MONITORING}/api/overview", timeout=5).json()
        jobs = ov.get("jobs", {})
        print(f"  Queue length:    {ov.get('queue_length')}")
        print(f"  Workers running: {ov.get('workers')}")
        print(f"  API replicas:    {ov.get('api_replicas')}")
        print(f"  Jobs completed/processing/failed: "
              f"{jobs.get('completed')}/{jobs.get('processing')}/{jobs.get('failed')}")
    except Exception as e:
        print(f"  [--] Overview unavailable: {e}")

    try:
        svcs = requests.get(f"{MONITORING}/api/health-summary", timeout=5).json().get("services", {})
        print("\n  Container health grid:")
        for name, info in sorted(svcs.items()):
            status = info.get("status", "?")
            health = info.get("health", "?")
            marker = "[OK]" if status == "running" and health in ("healthy", "none", "unknown") else "[--]"
            print(f"    {marker} {name:<26} {status:<10} health={health}")
    except Exception as e:
        print(f"  [--] Health summary unavailable: {e}")

    try:
        events = requests.get(f"{MONITORING}/api/events?limit=3", timeout=5).json().get("events", [])
        if events:
            print("\n  Latest autoscaler events:")
            for e in reversed(events):
                print(f"    [{str(e.get('timestamp'))[11:19]}] {e.get('message')}")
    except Exception:
        pass
    pause()

    # --- Step 5: Grafana ---
    print("\n[5/6] GRAFANA - PRE-PROVISIONED DASHBOARDS")
    print("-" * 70)
    try:
        r = requests.get(f"{GRAFANA}/api/search", timeout=5, auth=("admin", "admin"))
        if r.status_code == 200:
            boards = r.json()
            print(f"  Grafana reports {len(boards)} provisioned dashboard(s):")
            for d in boards:
                print(f"    - {d.get('title')}  (uid: {d.get('uid')})  -> {GRAFANA}/d/{d.get('uid')}")
        elif r.status_code == 401:
            print("  [--] admin/admin rejected — GRAFANA_PASSWORD env was customised.")
        else:
            print(f"  [--] Unexpected status {r.status_code}")
    except Exception as e:
        print(f"  [--] Cannot reach Grafana: {e}")
    print("  Datasource: Prometheus (provisioned) | auto-refresh: 10s")
    pause()

    # --- Step 6: Alertmanager + webhook round trip ---
    print("\n[6/6] ALERTMANAGER - ALERT ROUTING & WEBHOOK DELIVERY")
    print("-" * 70)
    try:
        r = requests.get(f"{ALERTMANAGER}/api/v2/status", timeout=5)
        print("  [OK] Alertmanager running" if r.status_code == 200
              else f"  [--] Status {r.status_code}")
    except Exception as e:
        print(f"  [--] Cannot reach Alertmanager: {e}")

    try:
        alerts = requests.get(f"{ALERTMANAGER}/api/v2/alerts", timeout=5).json()
        active = [a for a in alerts if a.get("status", {}).get("state") in ("active", "suppressed")]
        print(f"  Active alerts right now: {len(active)}")
        for a in active[:5]:
            print(f"    - {a.get('labels', {}).get('alertname', '?')}")
    except Exception:
        pass

    print("\n  End-to-end webhook delivery test (same path real alerts take):")
    payload = {"alerts": [{
        "status": "firing",
        "labels": {"alertname": "MonitoringDemoAlert", "severity": "warning"},
        "annotations": {"description": "synthetic alert from scripts/test_monitoring.py"},
        "startsAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }]}
    try:
        r = requests.post(f"{API}/api/webhooks/alertmanager", json=payload, timeout=5)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        print(f"  POST {API}/api/webhooks/alertmanager -> {r.status_code} {body}")
        if r.status_code == 200 and body.get("received"):
            print("  [OK] Auto-remediation endpoint accepted the alert (counted + audit-logged).")
    except Exception as e:
        print(f"  [--] Webhook call failed: {e}")

    print("\n  ALERT FLOW:")
    print("  services --/metrics--> Prometheus --rules--> Alertmanager")
    print("                                          |")
    print("                                          v")
    print("                     API POST /api/webhooks/alertmanager")
    print("                            (counters + audit log)")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
