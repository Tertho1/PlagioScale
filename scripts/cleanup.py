#!/usr/bin/env python3
"""
Clean up stuck/failed job state so batches can be recomputed.

By default shows a summary of job-state counts. Actions:

    --batch <id>     delete non-completed jobs for that batch (stuck
                     PENDING/PROCESSING rows block recompute for ~5 min)
    --dead-letter    clear Redis dead-letter entries and retry counters
    --failed         mark all FAILED jobs older than 1 day as CANCELLED

Usage:
    python scripts/cleanup.py                  # summary only
    python scripts/cleanup.py --batch <id>     # unstick one batch
    python scripts/cleanup.py --dead-letter    # purge dead letter + retries
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg
from common import redis_client

DB = dict(host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
          dbname=os.getenv("DB_NAME", "plagioscale"),
          user=os.getenv("DB_USER", "plagio"), password=os.getenv("DB_PASSWORD", "plagio_pass"))


def summary(cur):
    cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY status")
    print("Job states:")
    total = 0
    for status, n in cur.fetchall():
        print(f"  {status:<11} {n}")
        total += n
    print(f"  {'TOTAL':<11} {total}")

    cur.execute("""
        SELECT j.status, COUNT(*) FROM jobs j
        WHERE j.created_at < now() - interval '1 hour'
        GROUP BY j.status
    """)
    stale = {s: n for s, n in cur.fetchall() if s in ("PENDING", "PROCESSING")}
    if stale:
        print(f"\nStale (>1h) not-completed jobs: {sum(stale.values())} — consider --batch cleanup")

    try:
        r = redis_client()
        dl = r.scard("dead_letter_jobs")
        q = r.llen("job_queue")
        print(f"\nRedis: queue={q}, dead_letter={dl}")
    except Exception as e:
        print(f"\nRedis unavailable: {e}")


def clean_batch(cur, batch_id):
    cur.execute(
        "DELETE FROM jobs WHERE job_id LIKE %s AND status NOT IN ('COMPLETED','CANCELLED')",
        (f"batch-{batch_id}%",))
    print(f"Deleted {cur.rowcount} non-completed jobs for batch {batch_id[:8]}…")
    conn = cur.connection
    conn.commit()


def clear_dead_letter():
    r = redis_client()
    ids = list(r.smembers("dead_letter_jobs"))
    pipe = r.pipeline()
    for jid in ids:
        pipe.delete(f"dead_letter:{jid}")
    if ids:
        pipe.delete("dead_letter_jobs")
    pipe.delete("stale_job_retries")
    pipe.execute()
    print(f"Cleared {len(ids)} dead-letter entries + retry counters.")


def main():
    parser = argparse.ArgumentParser(description="PlagioScale job-state cleanup")
    parser.add_argument("--batch", help="Batch id whose stuck jobs should be deleted")
    parser.add_argument("--dead-letter", action="store_true",
                        help="Clear Redis dead letter + retry counters")
    args = parser.parse_args()

    did_something = False
    if args.dead_letter:
        clear_dead_letter()
        did_something = True
    if args.batch:
        with psycopg.connect(**DB) as conn, conn.cursor() as cur:
            clean_batch(cur, args.batch)
        did_something = True

    with psycopg.connect(**DB) as conn, conn.cursor() as cur:
        summary(cur)
    if not did_something:
        print("\n(no action requested — pass --batch or --dead-letter)")


if __name__ == "__main__":
    sys.exit(main())
