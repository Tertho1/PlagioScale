#!/usr/bin/env python3
"""
Inspect PlagioScale's PostgreSQL from the host machine.

Defaults to the most recent batches; pass --batch <id> for full detail
(submission scores, similarity rows, related jobs).

Usage:
    python scripts/debug_db.py                       # recent batch overview
    python scripts/debug_db.py --batch <batch_id>    # deep dive on one batch
    python scripts/debug_db.py --jobs 20             # latest worker jobs
"""

import argparse
import json
import os
import sys

import psycopg

DB_HOST = os.getenv("DB_HOST", "localhost")   # postgres is published on host :5432
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "plagioscale")
DB_USER = os.getenv("DB_USER", "plagio")
DB_PASSWORD = os.getenv("DB_PASSWORD", "plagio_pass")


def connect():
    try:
        return psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                               user=DB_USER, password=DB_PASSWORD, connect_timeout=5)
    except Exception as e:
        print(f"Cannot reach PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}: {e}")
        print("Is the stack running? (docker compose up -d)")
        sys.exit(1)


def recent_batches(cur, limit=8):
    cur.execute("""
        SELECT a.batch_id, a.name, a.created_at,
               COUNT(s.submission_id) AS subs,
               ROUND(AVG(s.ai_score)::numeric, 3) AS avg_ai,
               MAX(s.plagiarism_score) AS max_plag,
               (SELECT COUNT(*) FROM similarity_results r WHERE r.batch_id = a.batch_id) AS pairs
        FROM assignments a
        LEFT JOIN submissions s ON s.batch_id = a.batch_id AND s.status = 'ACTIVE'
        GROUP BY a.batch_id, a.name, a.created_at
        ORDER BY a.created_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    print(f"{'Batch':<10} {'Name':<32} {'Subs':>4} {'AvgAI':>6} {'MaxPlag':>8} {'Pairs':>6}  Created")
    print("-" * 92)
    for bid, name, created, subs, avg_ai, max_plag, pairs in rows:
        name = (name or "")[:31]
        avg_ai = f"{avg_ai:.3f}" if avg_ai is not None else "-"
        max_plag = f"{max_plag:.3f}" if max_plag is not None else "-"
        print(f"{bid[:8]}…   {name:<32} {subs:>4} {avg_ai:>6} {max_plag:>8} {pairs:>6}  "
              f"{created:%Y-%m-%d %H:%M}")
    if rows:
        print(f"\nDeep dive: python scripts/debug_db.py --batch {rows[0][0]}")


def batch_detail(cur, batch_id):
    cur.execute("SELECT name, access_code, created_at FROM assignments WHERE batch_id = %s",
                (batch_id,))
    row = cur.fetchone()
    if not row:
        print(f"No assignment {batch_id}")
        sys.exit(1)
    print(f"Assignment: {row[0]}  (access code {row[1]}, created {row[2]:%Y-%m-%d %H:%M})")

    print("\nSubmissions:")
    cur.execute("""
        SELECT submission_id, roll, status, ai_score, plagiarism_score, original_filename
        FROM submissions WHERE batch_id = %s ORDER BY created_at
    """, (batch_id,))
    for sid, roll, status, ai, plag, fname in cur.fetchall():
        ai_s = f"{ai:.3f}" if ai is not None else "-"
        plag_s = f"{plag:.3f}" if plag is not None else "-"
        print(f"  {sid[:8]}…  roll={roll:<10} status={status:<9} ai={ai_s:<6} plag={plag_s:<6} file={fname}")

    print("\nSimilarity pairs:")
    cur.execute("""
        SELECT submission_id_1, submission_id_2, similarity_score
        FROM similarity_results WHERE batch_id = %s
        ORDER BY similarity_score DESC LIMIT 15
    """, (batch_id,))
    pairs = cur.fetchall()
    for s1, s2, score in pairs:
        print(f"  {s1[:8]}… <-> {s2[:8]}…  {score:.4f}")
    if not pairs:
        print("  (none computed)")

    print("\nRelated jobs:")
    cur.execute("""
        SELECT job_id, status, error, created_at FROM jobs
        WHERE job_id LIKE %s ORDER BY created_at DESC LIMIT 10
    """, (f"batch-{batch_id}%",))
    jobs = cur.fetchall()
    for jid, status, error, created in jobs:
        suffix = f"  error={error[:60]}" if error else ""
        print(f"  …{jid[-12:]}  {status:<10} {created:%H:%M:%S}{suffix}")
    if not jobs:
        print("  (none)")


def latest_jobs(cur, limit=20):
    cur.execute("""SELECT job_id, status, worker_id, error, created_at
                   FROM jobs ORDER BY created_at DESC LIMIT %s""", (limit,))
    print(f"{'Job':<30} {'Status':<11} {'Worker':<14} Created      Error")
    print("-" * 100)
    for jid, status, worker, error, created in cur.fetchall():
        print(f"…{jid[-26:]:<28}  {status:<10}  {(worker or '-')[:13]:<13} "
              f"{created:%m-%d %H:%M:%S}  {(error or '')[:40]}")


def main():
    parser = argparse.ArgumentParser(description="Inspect PlagioScale database")
    parser.add_argument("--batch", help="Batch id for detailed view")
    parser.add_argument("--jobs", type=int, metavar="N", help="Show N latest jobs")
    parser.add_argument("--limit", type=int, default=8, help="Batches to list (default 8)")
    args = parser.parse_args()

    with connect() as conn, conn.cursor() as cur:
        if args.batch:
            batch_detail(cur, args.batch)
        elif args.jobs:
            latest_jobs(cur, args.jobs)
        else:
            recent_batches(cur, args.limit)


if __name__ == "__main__":
    main()
