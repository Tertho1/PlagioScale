#!/usr/bin/env python3
"""
Stress test — floods the real detection pipeline and verifies autoscaling.

Submits many files to a throwaway batch through /portal/submit, which enqueues
actual AI_DETECTION + SIMILARITY_COMPUTE jobs. (The old approach of POSTing
single texts to /submit no longer exercises anything: those jobs are
deprecated and skipped by the worker.) While the queue drains we watch the
monitoring dashboard's view of queue depth and worker count, then compare
autoscaler events to prove the system reacted to load.

Usage:
    python scripts/stress_test.py                # 12 files, 4 threads
    python scripts/stress_test.py 30 8           # 30 files, 8 threads
    python scripts/stress_test.py --keep         # keep the batch afterwards
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, MONITORING, PlagioClient, autoscaler_events, print_events

PARAGRAPH = (
    "Plagiarism detection compares student submissions against each other and "
    "against reference corpora. Modern systems blend lexical matching with "
    "semantic embeddings so paraphrased copying is still caught. "
)

SAMPLE_TEXTS = [
    f"Essay variant {i}: " + PARAGRAPH * 3 for i in range(1, 9)
]


def overview():
    try:
        r = requests.get(f"{MONITORING}/api/overview", timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="PlagioScale pipeline stress test")
    parser.add_argument("num_files", nargs="?", type=int, default=12,
                        help="Files to submit (default: 12)")
    parser.add_argument("threads", nargs="?", type=int, default=4,
                        help="Concurrent submission threads (default: 4)")
    parser.add_argument("--keep", action="store_true",
                        help="Keep the stress batch instead of deleting it")
    args = parser.parse_args()

    print("=" * 62)
    print("PlagioScale - Pipeline Stress Test")
    print("=" * 62)

    client = PlagioClient()
    if not client.login_or_signup():
        sys.exit(1)
    print(f"Authenticated as {client.user.get('email')}")

    r = client.post(f"{API}/portal/assignments",
                    json={"name": f"Stress Test {int(time.time())}"}, timeout=10)
    assert r.status_code == 200, r.text
    batch = r.json()
    batch_id, access_code = batch["batch_id"], batch["access_code"]
    print(f"Batch: {batch_id[:8]}…  (access code {access_code})")

    # ── Phase 1: flood submissions ────────────────────────────────────────
    print(f"\n[1/3] Submitting {args.num_files} files ({args.threads} threads)...")
    latencies, errors = [], []

    def submit(i):
        roll = f"T{i:03d}"
        text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)] + f" Unique tail {i}."
        start = time.time()
        try:
            resp = client.post(
                f"{API}/portal/submit",
                files={"file": (f"{roll}.txt", text.encode(), "text/plain")},
                data={"batch_id": batch_id, "roll": roll, "name": f"{roll} Student"},
                timeout=20,
            )
            latencies.append(time.time() - start)
            if resp.status_code == 429:
                time.sleep(5)          # rate limited: retry once after backoff
                resp = client.post(
                    f"{API}/portal/submit",
                    files={"file": (f"{roll}.txt", text.encode(), "text/plain")},
                    data={"batch_id": batch_id, "roll": roll, "name": f"{roll} Student"},
                    timeout=20,
                )
            resp.raise_for_status()
            return True
        except Exception as e:
            errors.append(str(e))
            return False

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = [pool.submit(submit, i) for i in range(args.num_files)]
        ok = sum(1 for f in as_completed(futures) if f.result())
    submit_secs = time.time() - t0
    print(f"  Submitted {ok}/{args.num_files} in {submit_secs:.1f}s "
          f"(avg {sum(latencies)/max(len(latencies),1)*1000:.0f}ms, errors {len(errors)})")

    if errors:
        for e in errors[:3]:
            print(f"    ! {e[:100]}")

    # Force one full recompute: the auto-enqueued jobs fire as soon as the 2nd
    # file lands, so during a fast burst they only cover the earliest
    # submissions. An explicit compute guarantees every file is scored.
    r = client.post(f"{API}/portal/compute-similarity/{batch_id}", timeout=10)
    print(f"  Full recompute queued: {'OK' if r.status_code == 200 else r.text[:80]}")

    # ── Phase 2: watch queue drain + workers ──────────────────────────────
    print("\n[2/3] Monitoring queue drain & autoscaler...")
    print(f"  {'Time':>5}  {'Queue':>6}  {'Workers':>7}  {'Scored':>7}")
    deadline = time.time() + 420
    scored = -1
    peak_queue, peak_workers = 0, 0
    last_print = 0
    while time.time() < deadline:
        ov = overview()
        q = ov.get("queue_length", 0)
        w = ov.get("workers", 0)
        peak_queue, peak_workers = max(peak_queue, q), max(peak_workers, w)
        r = client.get(f"{API}/portal/submissions/{batch_id}", timeout=10)
        subs = r.json().get("submissions", []) if r.status_code == 200 else []
        new_scored = sum(1 for s in subs
                         if s.get("ai_score") is not None and s.get("plagiarism_score") is not None)
        now = time.time()
        if new_scored != scored or now - last_print >= 10:
            print(f"  {int(now-t0):>4}s  {q:>6}  {w:>7}  {new_scored:>6}/{len(subs)}")
            scored, last_print = new_scored, now
        if subs and len(subs) >= ok and new_scored == len(subs):
            break
        time.sleep(2)

    drain_secs = time.time() - t0 - submit_secs

    # ── Phase 3: results ──────────────────────────────────────────────────
    r = client.get(f"{API}/portal/submissions/{batch_id}", timeout=10)
    subs = r.json().get("submissions", [])
    ai_scores = [s["ai_score"] for s in subs if s.get("ai_score") is not None]
    plag = [s["plagiarism_score"] for s in subs if s.get("plagiarism_score") is not None]

    print("\n[3/3] Results")
    print("-" * 62)
    print(f"  Submissions OK:      {ok}/{args.num_files}")
    print(f"  Submit throughput:   {ok/submit_secs:.2f} files/s")
    print(f"  Queue drain time:    {drain_secs:.1f}s")
    print(f"  Peak queue depth:    {peak_queue}")
    print(f"  Peak worker count:   {peak_workers}")
    if ai_scores:
        print(f"  AI scores:           n={len(ai_scores)} avg={sum(ai_scores)/len(ai_scores):.3f}")
    if plag:
        print(f"  Plagiarism scores:   n={len(plag)} max={max(plag):.3f}")

    events = autoscaler_events(limit=8, message_prefixes=("scaled",))
    if events:
        print("\n  Autoscaler actions during test:")
        print_events(list(reversed(events)))

    verdict = ok >= args.num_files * 0.8 and len(ai_scores) >= int(ok * 0.8)
    print(f"\n  STRESS TEST {'PASSED' if verdict else 'FAILED'} "
          f"(>=80% submitted and scored required)")

    if not args.keep:
        client.delete(f"{API}/portal/assignments/{batch_id}", timeout=15)
        print("  Stress batch deleted.")
    else:
        print(f"  Batch kept: {batch_id}")

    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
