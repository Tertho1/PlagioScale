"""Database persistence layer for PlagioScale jobs."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "plagioscale")
DB_USER = os.getenv("DB_USER", "plagio")
DB_PASSWORD = os.getenv("DB_PASSWORD", "plagio_pass")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Assignment(Base):
    """Assignment/Batch metadata."""

    __tablename__ = "assignments"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    access_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    allowed_file_types: Mapped[str] = mapped_column(Text, nullable=False, default=".pdf,.docx,.txt")
    allow_anonymous: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class Submission(Base):
    """Student submission for an assignment."""

    __tablename__ = "submissions"

    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    roll: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    embedding_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    plagiarism_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class User(Base):
    """User account for assignment owners and students (minimal)."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class SimilarityResult(Base):
    """Pairwise similarity between submissions."""

    __tablename__ = "similarity_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_id_1: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_id_2: Mapped[str] = mapped_column(String(64), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


class Notification(Base):
    """Outbound email notification queue."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent: Mapped[bool] = mapped_column(Integer, default=0)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(max_retries: int = 5, delay: float = 2.0) -> bool:
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as exc:
            print(f"⚠ Database init failed (table creation): {exc}")
            if attempt < max_retries - 1:
                print(f"  Retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            return False
        try:
            migrate_db()
        except Exception as exc:
            print(f"⚠ Database migration failed (non-fatal): {exc}")
        return True
    return False


def migrate_db() -> None:
    """Apply lightweight, idempotent schema migrations for existing databases."""
    statements = [
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(64)",
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS similarity_threshold FLOAT NOT NULL DEFAULT 0.5",
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS due_date TIMESTAMP",
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS allowed_file_types TEXT NOT NULL DEFAULT '.pdf,.docx,.txt'",
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS allow_anonymous INTEGER NOT NULL DEFAULT 1",
        "CREATE INDEX IF NOT EXISTS idx_assignments_owner_user_id ON assignments (owner_user_id)",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE'",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS email VARCHAR(256)",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS user_id VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions (user_id)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_batch_id ON submissions (batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions (status)",
        "CREATE INDEX IF NOT EXISTS idx_similarity_results_batch_id ON similarity_results (batch_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)",
        "DROP INDEX IF EXISTS ux_submissions_batch_roll",
    ]
    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except Exception as exc:
                print(f"⚠ Migration statement skipped: {exc}")

    # unique partial index — handle duplicates gracefully
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_submissions_active_batch_roll "
                    "ON submissions (batch_id, roll) WHERE status = 'ACTIVE'"
                )
            )
    except Exception as exc:
        # duplicates exist — remove them and retry
        print(f"⚠ Removing duplicate submissions for unique index: {exc}")
        with get_session() as session:
            dups = session.execute(
                text(
                    "SELECT batch_id, roll FROM submissions WHERE status = 'ACTIVE' "
                    "GROUP BY batch_id, roll HAVING COUNT(*) > 1"
                )
            ).fetchall()
            for batch_id, roll in dups:
                rows = session.execute(
                    text(
                        "SELECT submission_id FROM submissions "
                        "WHERE batch_id = :b AND roll = :r AND status = 'ACTIVE' "
                        "ORDER BY created_at DESC"
                    ),
                    {"b": batch_id, "r": roll},
                ).fetchall()
                # keep the newest, cancel the rest
                for row in rows[1:]:
                    session.execute(
                        text("UPDATE submissions SET status = 'CANCELLED' WHERE submission_id = :sid"),
                        {"sid": row[0]},
                    )
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_submissions_active_batch_roll "
                        "ON submissions (batch_id, roll) WHERE status = 'ACTIVE'"
                    )
                )
        except Exception as exc2:
            print(f"⚠ Could not create unique index even after cleanup: {exc2}")


def create_job_record(job_id: str, text: str, status: str = "PENDING") -> bool:
    try:
        with get_session() as session:
            existing = session.get(JobRecord, job_id)
            if existing:
                existing.text = text
                existing.status = status
                existing.updated_at = datetime.now(timezone.utc)
                return True

            session.add(JobRecord(job_id=job_id, text=text, status=status))
        return True
    except Exception as exc:
        print(f"⚠ Failed creating job record {job_id}: {exc}")
        return False


def update_job_status(
    job_id: str,
    status: str,
    worker_id: Optional[str] = None,
    error: Optional[str] = None,
) -> bool:
    try:
        with get_session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                return False
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if worker_id:
                record.worker_id = worker_id
            if error:
                record.error = error
            if status in ("COMPLETED", "FAILED"):
                record.completed_at = datetime.now(timezone.utc)
        return True
    except Exception as exc:
        print(f"⚠ Failed updating status for {job_id}: {exc}")
        return False


def store_job_result(
    job_id: str, result: dict, worker_id: Optional[str] = None
) -> bool:
    try:
        with get_session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                return False
            record.result_json = json.dumps(result)
            record.status = "COMPLETED"
            record.updated_at = datetime.now(timezone.utc)
            record.completed_at = datetime.now(timezone.utc)
            if worker_id:
                record.worker_id = worker_id
        return True
    except Exception as exc:
        print(f"⚠ Failed storing result for {job_id}: {exc}")
        return False


def get_job_record(job_id: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                return None

            result = None
            if record.result_json:
                try:
                    result = json.loads(record.result_json)
                except Exception:
                    result = None

            return {
                "job_id": record.job_id,
                "status": record.status,
                "result": result,
                "error": record.error,
                "worker_id": record.worker_id,
                "created_at": (
                    record.created_at.isoformat() if record.created_at else None
                ),
                "updated_at": (
                    record.updated_at.isoformat() if record.updated_at else None
                ),
                "completed_at": (
                    record.completed_at.isoformat() if record.completed_at else None
                ),
            }
    except Exception as exc:
        print(f"⚠ Failed reading record {job_id}: {exc}")
        return None


# Assignment and Submission helpers
def create_assignment(
    batch_id: str,
    name: str,
    access_code: str,
    expected_count: int = 0,
    owner_user_id: Optional[str] = None,
    similarity_threshold: float = 0.5,
    due_date: Optional[datetime] = None,
    allowed_file_types: str = ".pdf,.docx,.txt",
    allow_anonymous: bool = True,
) -> bool:
    try:
        with get_session() as session:
            session.add(
                Assignment(
                    batch_id=batch_id,
                    name=name,
                    access_code=access_code,
                    expected_count=expected_count,
                    owner_user_id=owner_user_id,
                    similarity_threshold=similarity_threshold,
                    due_date=due_date,
                    allowed_file_types=allowed_file_types,
                    allow_anonymous=allow_anonymous,
                )
            )
        return True
    except Exception as exc:
        print(f"⚠ Failed creating assignment {batch_id}: {exc}")
        return False


def create_submission(
    submission_id: str,
    batch_id: str,
    roll: str,
    name: Optional[str],
    email: Optional[str],
    filename: str,
    file_path: str,
    user_id: Optional[str] = None,
) -> dict:
    """
    Create a new submission, cancelling any previous active submission for the same (batch, roll).

    Returns a dict with:
        success: bool
        cancelled_submission_id: Optional[str] - ID of previously active submission that was cancelled
        cancelled_file_path: Optional[str] - file path of the cancelled submission (for cleanup)
    """
    result = {"success": False, "cancelled_submission_id": None, "cancelled_file_path": None}
    try:
        with get_session() as session:
            existing = (
                session.query(Submission)
                .filter(
                    Submission.batch_id == batch_id,
                    Submission.roll == roll,
                    Submission.status == "ACTIVE",
                )
                .with_for_update()
                .first()
            )
            cancelled_id = None
            cancelled_path = None
            if existing:
                cancelled_id = existing.submission_id
                cancelled_path = existing.file_path
                existing.status = "CANCELLED"
            session.add(
                Submission(
                    submission_id=submission_id,
                    batch_id=batch_id,
                    user_id=user_id,
                    roll=roll,
                    name=name,
                    email=email,
                    filename=filename,
                    file_path=file_path,
                    status="ACTIVE",
                )
            )
        result["success"] = True
        result["cancelled_submission_id"] = cancelled_id
        result["cancelled_file_path"] = cancelled_path
        return result
    except Exception as exc:
        print(f"⚠ Failed creating submission {submission_id}: {exc}")
        return result


def get_submission_by_id(submission_id: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = session.get(Submission, submission_id)
            if not record:
                return None
            return {
                "submission_id": record.submission_id,
                "batch_id": record.batch_id,
                "user_id": record.user_id,
                "roll": record.roll,
                "name": record.name,
                "email": record.email,
                "filename": record.filename,
                "file_path": record.file_path,
                "status": record.status,
                "ai_score": record.ai_score,
                "plagiarism_score": record.plagiarism_score,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading submission {submission_id}: {exc}")
        return None


def get_submissions_by_batch(batch_id: str, limit: int = None, offset: int = 0) -> list:
    try:
        with get_session() as session:
            q = (
                session.query(Submission)
                .filter(Submission.batch_id == batch_id, Submission.status == "ACTIVE")
                .order_by(Submission.created_at)
            )
            if limit is not None:
                q = q.limit(limit).offset(offset)
            records = q.all()
            return [
                {
                    "submission_id": r.submission_id,
                    "roll": r.roll,
                    "name": r.name,
                    "email": r.email,
                    "file_path": r.file_path,
                    "status": r.status,
                    "plagiarism_score": r.plagiarism_score,
                    "ai_score": r.ai_score,
                    "embedding_json": r.embedding_json,
                }
                for r in records
            ]
    except Exception as exc:
        print(f"⚠ Failed fetching submissions for batch {batch_id}: {exc}")
        return []


def get_submissions_by_user(user_id: str) -> list:
    try:
        with get_session() as session:
            records = (
                session.query(Submission)
                .filter(Submission.user_id == user_id, Submission.status == "ACTIVE")
                .all()
            )
            return [
                {
                    "submission_id": r.submission_id,
                    "batch_id": r.batch_id,
                    "roll": r.roll,
                    "name": r.name,
                    "email": r.email,
                    "filename": r.filename,
                    "file_path": r.file_path,
                    "status": r.status,
                    "plagiarism_score": r.plagiarism_score,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in records
            ]
    except Exception as exc:
        print(f"Failed fetching submissions for user {user_id}: {exc}")
        return []


def get_assignment(batch_id: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = session.get(Assignment, batch_id)
            if not record:
                return None
            return {
                "batch_id": record.batch_id,
                "name": record.name,
                "access_code": record.access_code,
                "owner_user_id": record.owner_user_id,
                "expected_count": record.expected_count,
                "similarity_threshold": record.similarity_threshold,
                "due_date": record.due_date.isoformat() if record.due_date else None,
                "allowed_file_types": record.allowed_file_types,
                "allow_anonymous": bool(record.allow_anonymous),
                "created_at": (
                    record.created_at.isoformat() if record.created_at else None
                ),
            }
    except Exception as exc:
        print(f"⚠ Failed reading assignment {batch_id}: {exc}")
        return None


def get_assignment_by_access_code(access_code: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = (
                session.query(Assignment)
                .filter(Assignment.access_code == access_code)
                .first()
            )
            if not record:
                return None
            return {
                "batch_id": record.batch_id,
                "name": record.name,
                "access_code": record.access_code,
                "owner_user_id": record.owner_user_id,
                "expected_count": record.expected_count,
                "similarity_threshold": record.similarity_threshold,
                "due_date": record.due_date.isoformat() if record.due_date else None,
                "allowed_file_types": record.allowed_file_types,
                "allow_anonymous": bool(record.allow_anonymous),
                "created_at": (
                    record.created_at.isoformat() if record.created_at else None
                ),
            }
    except Exception as exc:
        print(f"⚠ Failed reading assignment by access code {access_code}: {exc}")
        return None


def list_assignments() -> list:
    try:
        with get_session() as session:
            records = session.query(Assignment).order_by(Assignment.created_at.desc()).all()
            return [
                {
                    "batch_id": r.batch_id,
                    "name": r.name,
                    "access_code": r.access_code,
                    "owner_user_id": r.owner_user_id,
                    "expected_count": r.expected_count,
                    "similarity_threshold": r.similarity_threshold,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "allowed_file_types": r.allowed_file_types,
                    "allow_anonymous": bool(r.allow_anonymous),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
    except Exception as exc:
        print(f"⚠ Failed listing assignments: {exc}")
        return []


def get_active_submission_by_batch_and_roll(batch_id: str, roll: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = (
                session.query(Submission)
                .filter(
                    Submission.batch_id == batch_id,
                    Submission.roll == roll,
                    Submission.status == "ACTIVE",
                )
                .first()
            )
            if not record:
                return None
            return {
                "submission_id": record.submission_id,
                "batch_id": record.batch_id,
                "roll": record.roll,
                "name": record.name,
                "email": record.email,
                "filename": record.filename,
                "file_path": record.file_path,
                "status": record.status,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading active submission for {batch_id}/{roll}: {exc}")
        return None


def get_submissions_count_by_batch(batch_id: str) -> int:
    try:
        with get_session() as session:
            return session.query(Submission).filter(
                Submission.batch_id == batch_id, Submission.status == "ACTIVE"
            ).count()
    except Exception as exc:
        print(f"⚠ Failed counting submissions for batch {batch_id}: {exc}")
        return 0


def update_submission_status(submission_id: str, status: str) -> bool:
    try:
        with get_session() as session:
            record = session.get(Submission, submission_id)
            if not record:
                return False
            record.status = status
        return True
    except Exception as exc:
        print(f"⚠ Failed updating submission {submission_id}: {exc}")
        return False


def update_submission_ai_score(submission_id: str, ai_score: float) -> bool:
    """Update the AI detection score for a single submission."""
    try:
        with get_session() as session:
            record = session.get(Submission, submission_id)
            if record:
                record.ai_score = ai_score
        return True
    except Exception as exc:
        print(f"⚠ Failed updating ai_score for {submission_id}: {exc}")
        return False


def store_submission_embedding(submission_id: str, embedding: list) -> bool:
    try:
        with get_session() as session:
            record = (
                session.query(Submission)
                .filter(Submission.submission_id == submission_id)
                .first()
            )
            if record:
                record.embedding_json = json.dumps(embedding)
        return True
    except Exception as exc:
        print(f"⚠ Failed storing embedding for {submission_id}: {exc}")
        return False


def store_similarity_results(batch_id: str, results: dict) -> bool:
    """Store pairwise similarity results."""
    try:
        with get_session() as session:
            # Clear existing results for this batch
            session.query(SimilarityResult).filter(
                SimilarityResult.batch_id == batch_id
            ).delete()
            # Insert new results
            for sub_id_1, scores in results.items():
                for sub_id_2, score in scores.items():
                    if sub_id_1 < sub_id_2:  # avoid duplicates
                        session.add(
                            SimilarityResult(
                                batch_id=batch_id,
                                submission_id_1=sub_id_1,
                                submission_id_2=sub_id_2,
                                similarity_score=score,
                            )
                        )
        return True
    except Exception as exc:
        print(f"⚠ Failed storing similarity results for batch {batch_id}: {exc}")
        return False


def get_similarity_matrix(batch_id: str) -> dict:
    """Retrieve similarity matrix for a batch."""
    try:
        with get_session() as session:
            records = (
                session.query(SimilarityResult)
                .filter(SimilarityResult.batch_id == batch_id)
                .all()
            )
            matrix = {}
            for r in records:
                if r.submission_id_1 not in matrix:
                    matrix[r.submission_id_1] = {}
                if r.submission_id_2 not in matrix:
                    matrix[r.submission_id_2] = {}
                matrix[r.submission_id_1][r.submission_id_2] = r.similarity_score
                matrix[r.submission_id_2][r.submission_id_1] = r.similarity_score
        return matrix
    except Exception as exc:
        print(f"⚠ Failed retrieving similarity matrix for batch {batch_id}: {exc}")
        return {}


## User helpers
def create_user(user_id: str, email: str, name: Optional[str], password_hash: str, role: str = "user") -> bool:
    try:
        with get_session() as session:
            session.add(
                User(
                    user_id=user_id,
                    email=email,
                    name=name,
                    password_hash=password_hash,
                    role=role,
                    token_version=0,
                )
            )
        return True
    except Exception as exc:
        print(f"⚠ Failed creating user {email}: {exc}")
        return False


def get_user_by_email(email: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = session.query(User).filter(User.email == email).first()
            if not record:
                return None
            return {
                "user_id": record.user_id,
                "email": record.email,
                "name": record.name,
                "role": record.role,
                "password_hash": record.password_hash,
                "token_version": record.token_version,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading user by email {email}: {exc}")
        return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    try:
        with get_session() as session:
            record = session.get(User, user_id)
            if not record:
                return None
            return {
                "user_id": record.user_id,
                "email": record.email,
                "name": record.name,
                "role": record.role,
                "token_version": record.token_version,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading user {user_id}: {exc}")
        return None


def get_paginated_users(search: str = "", page: int = 1, per_page: int = 20) -> dict:
    try:
        with get_session() as session:
            query = session.query(User)
            if search:
                pattern = f"%{search}%"
                query = query.filter(
                    User.email.ilike(pattern) | User.name.ilike(pattern)
                )
            total = query.count()
            records = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
            users = [
                {
                    "user_id": r.user_id,
                    "email": r.email,
                    "name": r.name,
                    "role": r.role,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
            return {"users": users, "total": total, "page": page, "per_page": per_page}
    except Exception as exc:
        print(f"⚠ Failed listing users: {exc}")
        return {"users": [], "total": 0, "page": page, "per_page": per_page}


def update_user_role(user_id: str, new_role: str) -> bool:
    try:
        with get_session() as session:
            record = session.get(User, user_id)
            if not record:
                return False
            record.role = new_role
            record.token_version = (record.token_version or 0) + 1
            return True
    except Exception as exc:
        print(f"⚠ Failed updating role for {user_id}: {exc}")
        return False


def get_admin_stats() -> dict:
    try:
        with get_session() as session:
            total_users = session.query(User).count()
            total_assignments = session.query(Assignment).count()
            total_submissions = session.query(Submission).count()
            active_submissions = session.query(Submission).filter(Submission.status == "ACTIVE").count()
            total_similarity_results = session.query(SimilarityResult).count()
            pending_notifications = session.query(Notification).filter(Notification.sent == 0).count()
            return {
                "total_users": total_users,
                "total_assignments": total_assignments,
                "total_submissions": total_submissions,
                "active_submissions": active_submissions,
                "total_similarity_results": total_similarity_results,
                "pending_notifications": pending_notifications,
            }
    except Exception as exc:
        print(f"⚠ Failed getting admin stats: {exc}")
        return {}


def get_cross_batch_comparisons(batch_id_1: str, batch_id_2: str) -> list:
    try:
        with get_session() as session:
            subs_1 = (
                session.query(Submission)
                .filter(Submission.batch_id == batch_id_1, Submission.status == "ACTIVE")
                .all()
            )
            subs_2 = (
                session.query(Submission)
                .filter(Submission.batch_id == batch_id_2, Submission.status == "ACTIVE")
                .all()
            )
            results = []
            for s1 in subs_1:
                for s2 in subs_2:
                    result = (
                        session.query(SimilarityResult)
                        .filter(
                            SimilarityResult.batch_id == batch_id_1,
                            SimilarityResult.submission_id_1 == s1.submission_id,
                            SimilarityResult.submission_id_2 == s2.submission_id,
                        )
                        .first()
                    )
                    if result:
                        results.append(
                            {
                                "batch_id_1": batch_id_1,
                                "batch_id_2": batch_id_2,
                                "submission_id_1": s1.submission_id,
                                "roll_1": s1.roll,
                                "name_1": s1.name,
                                "submission_id_2": s2.submission_id,
                                "roll_2": s2.roll,
                                "name_2": s2.name,
                                "similarity_score": result.similarity_score,
                            }
                        )
            results.sort(key=lambda r: r["similarity_score"], reverse=True)
            return results
    except Exception as exc:
        print(f"⚠ Failed cross-batch comparison: {exc}")
        return []


def get_student_comparison_details(submission_id: str) -> list:
    try:
        with get_session() as session:
            sub = session.get(Submission, submission_id)
            if not sub:
                return []
            results = (
                session.query(SimilarityResult)
                .filter(
                    SimilarityResult.batch_id == sub.batch_id,
                    (SimilarityResult.submission_id_1 == submission_id)
                    | (SimilarityResult.submission_id_2 == submission_id),
                )
                .all()
            )
            pairs = []
            for r in results:
                other_id = r.submission_id_2 if r.submission_id_1 == submission_id else r.submission_id_1
                other = session.get(Submission, other_id)
                pairs.append(
                    {
                        "submission_id": submission_id,
                        "roll": sub.roll,
                        "name": sub.name,
                        "ai_score": sub.ai_score,
                        "plagiarism_score": sub.plagiarism_score,
                        "compared_with_id": other_id,
                        "compared_with_roll": other.roll if other else "?",
                        "compared_with_name": other.name if other else "?",
                        "similarity_score": r.similarity_score,
                    }
                )
            pairs.sort(key=lambda p: p["similarity_score"], reverse=True)
            return pairs
    except Exception as exc:
        print(f"⚠ Failed loading comparison details: {exc}")
        return []


def create_notification(user_id: str, email: str, subject: str, body: str) -> bool:
    try:
        with get_session() as session:
            notification = Notification(
                id=None,
                user_id=user_id,
                email=email,
                subject=subject,
                body=body,
                sent=0,
            )
            session.add(notification)
            return True
    except Exception as exc:
        print(f"⚠ Failed creating notification for {user_id}: {exc}")
        return False


def get_pending_notifications(limit: int = 50) -> list:
    try:
        with get_session() as session:
            records = (
                session.query(Notification)
                .filter(Notification.sent == 0)
                .order_by(Notification.created_at.asc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "email": r.email,
                    "subject": r.subject,
                    "body": r.body,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
    except Exception as exc:
        print(f"⚠ Failed reading pending notifications: {exc}")
        return []


def mark_notification_sent(notification_id: int) -> bool:
    try:
        with get_session() as session:
            record = session.get(Notification, notification_id)
            if not record:
                return False
            record.sent = 1
            record.sent_at = _utcnow()
            return True
    except Exception as exc:
        print(f"⚠ Failed marking notification sent: {exc}")
        return False
