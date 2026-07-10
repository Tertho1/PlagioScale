"""
Seed data script — populates PostgreSQL with demo batches, submissions, users.

Usage:
    python scripts/seed_test_data.py          # default: 2 batches, 5 students each
    python scripts/seed_test_data.py --batches 3 --students 10
"""

import argparse
import hashlib
import random
import string
import sys
import uuid
from datetime import datetime, timezone

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import get_db_connection, init_db
from shared.models import UserRole


SAMPLE_TEXTS = [
    "Machine learning is a powerful tool for data analysis and prediction in modern computing systems.",
    "Cloud computing revolutionizes how we deploy and scale applications across distributed infrastructure.",
    "Artificial intelligence is transforming industries globally through automation and intelligent decision-making.",
    "Distributed systems enable scalable applications by partitioning work across multiple nodes efficiently.",
    "Containerization with Docker simplifies deployment by packaging applications with their dependencies.",
    "The rapid advancement in technology continues to reshape society and the way we interact with digital systems.",
    "Data science combines statistics and programming to extract meaningful insights from complex datasets.",
    "Microservices architecture allows independent scaling of services while maintaining loose coupling.",
    "Natural language processing enables computers to understand and generate human language effectively.",
    "Cybersecurity frameworks protect organizations from evolving threats through layered defense mechanisms.",
    "Machine learning models can identify patterns in data that humans might overlook during analysis.",
    "Cloud-native applications leverage containers and orchestration for resilient deployment at scale.",
    "Deep learning networks have achieved remarkable results in image recognition and natural language tasks.",
    "Agile development methodologies emphasize iterative progress through cross-functional team collaboration.",
    "Blockchain technology provides decentralized consensus mechanisms for trustless transaction verification.",
    "Edge computing brings computation closer to data sources reducing latency for real-time applications.",
    "Quantum computing promises exponential speedup for certain classes of mathematical optimization problems.",
    "DevOps practices bridge the gap between development and operations through continuous automation pipelines.",
    "The Internet of Things connects billions of devices creating vast networks of sensor data.",
    "Version control systems like Git enable collaborative software development with comprehensive history tracking.",
]


def random_student_email(i):
    names = ["alice", "bob", "charlie", "diana", "eve", "frank", "grace", "henry", "iris", "jack"]
    domains = ["university.edu", "college.edu", "institute.edu"]
    name = names[i % len(names)]
    return f"{name}.{random.randint(1000, 9999)}@{random.choice(domains)}"


def seed_database(batches=2, students_per_batch=5):
    """Seed the database with test data."""
    print(f"Seeding database: {batches} batches, {students_per_batch} students each")

    if not init_db():
        print("Error: Database not available")
        sys.exit(1)

    conn = get_db_connection()
    if not conn:
        print("Error: Could not connect to database")
        sys.exit(1)

    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    try:
        # Create admin user
        admin_id = str(uuid.uuid4())
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        cur.execute(
            "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING",
            (admin_id, "admin@plagioscale.local", admin_hash, UserRole.ADMIN.value, now)
        )
        print(f"  ✓ Admin user: admin@plagioscale.local / admin123")

        # Create batches
        for b in range(1, batches + 1):
            batch_id = str(uuid.uuid4())
            batch_name = f"Assignment {b} - {random.choice(['Essay', 'Report', 'Project', 'Thesis', 'Paper'])}"
            cur.execute(
                "INSERT INTO batches (id, name, created_by, created_at) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (batch_id, batch_name, admin_id, now)
            )
            print(f"\n  Batch {b}: {batch_name}")

            # Create students and submissions
            student_ids = []
            for s in range(1, students_per_batch + 1):
                user_id = str(uuid.uuid4())
                email = random_student_email((b - 1) * students_per_batch + s)
                pw_hash = hashlib.sha256(f"student{s}".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING",
                    (user_id, email, pw_hash, UserRole.STUDENT.value, now)
                )
                student_ids.append((user_id, email))

                # Create submission
                sub_id = str(uuid.uuid4())
                # Pick a text and optionally introduce some plagiarism
                base_idx = ((b - 1) * students_per_batch + s) % len(SAMPLE_TEXTS)
                text = SAMPLE_TEXTS[base_idx]
                # If s > 1, plagiarize from a random earlier submission in same batch
                if s > 1 and random.random() > 0.3:
                    prev_text = SAMPLE_TEXTS[(base_idx - 1) % len(SAMPLE_TEXTS)]
                    # Mix texts for moderate similarity
                    words_a = text.split()
                    words_b = prev_text.split()
                    mid = len(words_a) // 2
                    text = " ".join(words_a[:mid] + words_b[mid:])

                filename = f"{email.split('@')[0]}_submission.pdf"
                cur.execute("""
                    INSERT INTO submissions (id, batch_id, user_id, filename, original_text, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (sub_id, batch_id, user_id, filename, text, "COMPLETED", now))

                print(f"    ✓ {email:30s} → {filename}")

            # Create similarity matrix for batch
            matrix = []
            for i, (uid_i, _) in enumerate(student_ids):
                row = []
                for j, (uid_j, _) in enumerate(student_ids):
                    if i == j:
                        row.append(0.0)
                    elif j < i:
                        # Use already computed value (matrix is symmetric)
                        row.append(matrix[j][i])
                    else:
                        score = round(random.uniform(0.1, 0.95), 4)
                        row.append(score)
                matrix.append(row)

            import json
            cur.execute(
                "INSERT INTO similarity_matrices (batch_id, matrix_data, created_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (batch_id, json.dumps({"matrix": matrix}), now)
            )
            print(f"    ✓ Similarity matrix generated")

        conn.commit()
        print(f"\n✓ Database seeded successfully!")
        print(f"  Batches: {batches}")
        print(f"  Students: {batches * students_per_batch}")
        print(f"  Admin login: admin@plagioscale.local / admin123")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error seeding database: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed database with demo data")
    parser.add_argument("--batches", type=int, default=2, help="Number of batches to create")
    parser.add_argument("--students", type=int, default=5, help="Students per batch")
    args = parser.parse_args()

    seed_database(batches=args.batches, students_per_batch=args.students)
