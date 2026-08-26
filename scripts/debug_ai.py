#!/usr/bin/env python3
"""
Debug the AI-detection pipeline end to end with a known text.

Uploads the given text into a throwaway batch (plus one filler submission so
the batch qualifies for auto-compute), waits for the worker to persist
ai_score, and prints the full result. Cleans the batch up unless --keep.

Usage:
    python scripts/debug_ai.py                       # default sample text
    python scripts/debug_ai.py "Your text here..."   # custom text (>=50 chars)
    python scripts/debug_ai.py --keep                # keep the debug batch
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, PlagioClient

FILLER = (
    "The quarterly logistics review highlights steady improvements in warehouse "
    "throughput and carrier reliability. Route optimisation reduced average "
    "delivery latency by nine percent, while packaging changes cut damage claims. "
)

DEFAULT_TEXT = (
    "This is a diagnostic text for the AI detection pipeline. Large language "
    "models tend to produce fluent, evenly paced prose with low burstiness, "
    "which detectors try to separate from human writing quirks."
)


def main():
    parser = argparse.ArgumentParser(description="Debug AI detection pipeline")
    parser.add_argument("text", nargs="?", default=DEFAULT_TEXT,
                        help="Text to analyse (minimum 50 characters)")
    parser.add_argument("--keep", action="store_true", help="Keep the debug batch")
    args = parser.parse_args()

    if len(args.text.strip()) < 50:
        print("Text too short: portal self-submission requires >= 50 chars.")
        sys.exit(2)

    client = PlagioClient()
    if not client.login_or_signup():
        sys.exit(1)

    r = client.post(f"{API}/portal/assignments", json={"name": f"AIDebug {int(time.time())}"},
                    timeout=10)
    assert r.status_code == 200, r.text
    batch_id = r.json()["batch_id"]
    print(f"Batch: {batch_id}")

    uploads = [("target.txt", args.text), ("filler.txt", FILLER)]
    sub_ids = {}
    for name, content in uploads:
        roll = os.path.splitext(name)[0].upper()
        r = client.post(f"{API}/portal/submit",
                        files={"file": (name, content.encode(), "text/plain")},
                        data={"batch_id": batch_id, "roll": roll}, timeout=15)
        assert r.status_code == 200, r.text
        sub_ids[roll] = r.json()["submission_hash"]
        print(f"Uploaded {name}: {r.json()['submission_hash'][:8]}…")

    print("\nPolling for ai_score (worker runs RoBERTa + perplexity + stylometry)...")
    deadline = time.time() + 300
    scores = {}
    while time.time() < deadline:
        r = client.get(f"{API}/portal/submissions/{batch_id}", timeout=10)
        for s in r.json().get("submissions", []):
            if s.get("ai_score") is not None:
                scores[s["roll"]] = s["ai_score"]
        if len(scores) == len(sub_ids):
            break
        time.sleep(5)

    print("\nResult:")
    if len(scores) != len(sub_ids):
        print(f"  TIMEOUT — only {len(scores)}/{len(sub_ids)} scored within 300s.")
        print("  Check worker logs: docker logs plagioscale-worker-1 --tail 50")
        ok = False
    else:
        for roll, score in scores.items():
            label = ("AI-generated" if score >= 0.7 else
                     "human/assisted" if score <= 0.3 else "mixed signals")
            print(f"  {roll:<8} ai_score={score:.4f}  ({label})")
        ok = True

    if not args.keep:
        client.delete(f"{API}/portal/assignments/{batch_id}", timeout=15)
        print("\nDebug batch deleted.")
    else:
        print(f"\nBatch kept: {batch_id}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
