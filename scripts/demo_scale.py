#!/usr/bin/env python3
"""
Push a manual scale event into Redis (as the autoscaler does), so it shows up
in the monitoring dashboard's event feed. Useful for demoing the event
pipeline without waiting for a real scale decision.

Usage: python scripts/demo_scale.py [num_workers]
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import redis_client


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    r = redis_client()
    try:
        r.ping()
    except Exception as e:
        print(f"Cannot reach Redis ({e}). Is the stack running?")
        sys.exit(1)

    queue_len = r.llen("job_queue")
    event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": "info",
        "message": f"Manual scale to {n} workers (demo)",
        "queue_length": queue_len,
        "workers": n,
    }
    r.lpush("autoscaler_events", json.dumps(event))
    r.ltrim("autoscaler_events", 0, 99)
    print("Pushed demo event to Redis:", json.dumps(event))
    print("See it live at http://localhost:8090 (event feed)")


if __name__ == "__main__":
    main()
