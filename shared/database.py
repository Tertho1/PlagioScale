"""Database persistence layer for PlagioScale jobs."""

from __future__ import annotations

import json
import os
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


def init_db() -> bool:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"⚠ Database init failed (table creation): {exc}")
        return False
    try:
        migrate_db()
    except Exception as exc:
        print(f"⚠ Database migration failed (non-fatal): {exc}")
    return True


def migrate_db() -> None:
    """Apply lightweight, idempotent schema migrations for existing databases."""
    statements = [
        "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS idx_assignments_owner_user_id ON assignments (owner_user_id)",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE'",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS email VARCHAR(256)",
        "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS user_id VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions (user_id)",
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
) -> bool:
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
            if existing:
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
        return True
    except Exception as exc:
        print(f"⚠ Failed creating submission {submission_id}: {exc}")
        return False


def get_submissions_by_batch(batch_id: str) -> list:
    try:
        with get_session() as session:
            records = (
                session.query(Submission)
                .filter(Submission.batch_id == batch_id, Submission.status == "ACTIVE")
                .all()
            )
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
            records = session.query(Assignment).all()
            return [
                {
                    "batch_id": r.batch_id,
                    "name": r.name,
                    "access_code": r.access_code,
                    "owner_user_id": r.owner_user_id,
                    "expected_count": r.expected_count,
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
def create_user(user_id: str, email: str, name: Optional[str], password_hash: str) -> bool:
    try:
        with get_session() as session:
            session.add(
                User(
                    user_id=user_id,
                    email=email,
                    name=name,
                    password_hash=password_hash,
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
                "password_hash": record.password_hash,
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
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading user {user_id}: {exc}")
        return None
