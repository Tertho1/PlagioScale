#!/usr/bin/env python3
"""
Seed demo data through the live API: an instructor account, N assignments,
M student submissions each (with some deliberately plagiarised variants),
then waits until every batch has a computed similarity matrix.

Goes through the API instead of raw SQL so users are bcrypt-hashed correctly,
files land on the uploads volume, and the worker computes REAL similarity and
AI scores (the old SQL version inserted into tables that no longer exist).

Usage:
    python scripts/seed_test_data.py                        # 2 batches x 5
    python scripts/seed_test_data.py --batches 3 --students 10
    python scripts/seed_test_data.py --email me@x.dev --password 'S3cret!pw'
"""

import argparse
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import API, PlagioClient

BASE_TEXTS = [
    "Machine learning is a powerful tool for data analysis and prediction in modern computing systems.",
    "Cloud computing revolutionizes how we deploy and scale applications across distributed infrastructure.",
    "Artificial intelligence is transforming industries globally through automation and intelligent decisions.",
    "Distributed systems enable scalable applications by partitioning work across multiple nodes efficiently.",
    "Containerization with Docker simplifies deployment by packaging applications with their dependencies.",
    "Data science combines statistics and programming to extract meaningful insights from complex datasets.",
    "Microservices architecture allows independent scaling of services while maintaining loose coupling between components.",
    "Natural language processing enables computers to understand and generate human language effectively at scale.",
]
NAMES = ["alice", "bob", "charlie", "diana", "eve", "frank", "grace", "henry",
         "iris", "jack", "kate", "liam", "mia", "noah", "olivia", "peter"]

FILLER = (" In addition, the study highlights trade-offs between latency and "
          "throughput that practitioners should weigh when selecting architectures.")


def make_text(idx, plagiarise_from=None):
    base = BASE_TEXTS[idx % len(BASE_TEXTS)]
    if plagiarise_from is not None:
        src = BASE_TEXTS[plagiarise_from % len(BASE_TEXTS)]
        wa, wb = base.split(), src.split()
        text = " ".join(wa[:len(wa) // 2] + wb[len(wb) // 2:])  # spliced mid-sentence copy
    else:
        text = base
    return (text + FILLER * 2) * 2  # comfortably above minimum length


def wait_for_batch(client, batch_id, n_subs, timeout=180):
    """Wait until all submissions have plagiarism scores (matrix computed)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"{API}/portal/submissions/{batch_id}", timeout=10)
        subs = r.json().get("submissions", [])
        if len(subs) >= n_subs and all(s.get("plagiarism_score") is not None for s in subs):
            return True
        time.sleep(3)
    return False


def main():
    parser = argparse.ArgumentParser(description="Seed demo data via the live API")
    parser.add_argument("--batches", type=int, default=2)
    parser.add_argument("--students", type=int, default=5)
    parser.add_argument("--email", default="teacher@plagioscale.dev")
    parser.add_argument("--password", default="Teach123!")
    parser.add_argument("--name", default="Demo Teacher")
    args = parser.parse_args()

    print("=" * 62)
    print(f"Seeding {args.batches} batches x {args.students} students via the API")
    print("=" * 62)

    client = PlagioClient()
    r = client.post(f"{API}/auth/login", json={"email": args.email, "password": args.password},
                    timeout=10)
    if r.status_code != 200:
        r = client.post(f"{API}/auth/signup",
                        json={"email": args.email, "password": args.password,
                              "name": args.name, "role": "teacher"}, timeout=10)
        if r.status_code != 200:
            print(f"Could not create teacher account: {r.status_code} {r.text[:120]}")
            print("(If it exists with a different password, pass --email/--password.)")
            sys.exit(1)
        client.login_or_signup(args.email, args.password, args.name)
    else:
        client.login_or_signup(args.email, args.password, args.name)
    print(f"Authenticated as {args.email}")

    created = []
    for b in range(1, args.batches + 1):
        name = f"Seeded Assignment {b} — {time.strftime('%m-%d %H:%M')}"
        r = client.post(f"{API}/portal/assignments",
                        json={"name": name, "expected_count": args.students}, timeout=10)
        assert r.status_code == 200, r.text
        batch = r.json()
        batch_id, code = batch["batch_id"], batch["access_code"]
        print(f"\nBatch {b}: {name}")
        print(f"  id={batch_id}  access_code={code}")

        for s in range(1, args.students + 1):
            roll = f"STU{s:03d}"
            name_s = NAMES[(b - 1) * args.students + s - 1 % len(NAMES)]
            # every ~3rd student plagiarises from the previous student's source
            plag_from = (s - 2) if (s > 1 and s % 3 == 0) else None
            text = make_text((b - 1) * args.students + s - 1, plag_from)
            resp = client.post(f"{API}/portal/submit",
                               files={"file": (f"{name_s}.txt", text.encode(), "text/plain")},
                               data={"batch_id": batch_id, "roll": roll,
                                     "name": f"{name_s.title()} Student"},
                               timeout=15)
            mark = "✓" if resp.status_code == 200 else "✗"
            flag = " (plagiarised)" if plag_from is not None else ""
            print(f"    {mark} {roll} {name_s}{flag}")
            if resp.status_code == 429:      # rate limited — pace ourselves
                time.sleep(5)

        created.append((batch_id, code, name))

    print("\nWaiting for workers to compute similarity matrices...")
    for batch_id, code, name in created:
        ok = wait_for_batch(client, batch_id, args.students)
        state = "ready ✓" if ok else "TIMEOUT (check worker logs)"
        print(f"  {name[:40]:<42} {state}")

    print("\nSeed complete. Access codes:")
    for batch_id, code, name in created:
        print(f"  {code}  →  {name[:50]}")


if __name__ == "__main__":
    main()
