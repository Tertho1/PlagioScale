"""Database persistence layer for PlagioScale jobs."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "plagioscale")
DB_USER = os.getenv("DB_USER", "plagio")
DB_PASSWORD = os.getenv("DB_PASSWORD", "plagio_pass")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


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
        return True
    except Exception as exc:
        print(f"⚠ Database init failed: {exc}")
        return False


def create_job_record(job_id: str, text: str, status: str = "PENDING") -> bool:
    try:
        with get_session() as session:
            existing = session.get(JobRecord, job_id)
            if existing:
                existing.text = text
                existing.status = status
                existing.updated_at = datetime.utcnow()
                return True

            session.add(JobRecord(job_id=job_id, text=text, status=status))
        return True
    except Exception as exc:
        print(f"⚠ Failed creating job record {job_id}: {exc}")
        return False


def update_job_status(job_id: str, status: str, worker_id: Optional[str] = None, error: Optional[str] = None) -> bool:
    try:
        with get_session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                return False
            record.status = status
            record.updated_at = datetime.utcnow()
            if worker_id:
                record.worker_id = worker_id
            if error:
                record.error = error
            if status in ("COMPLETED", "FAILED"):
                record.completed_at = datetime.utcnow()
        return True
    except Exception as exc:
        print(f"⚠ Failed updating status for {job_id}: {exc}")
        return False


def store_job_result(job_id: str, result: dict, worker_id: Optional[str] = None) -> bool:
    try:
        with get_session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                return False
            record.result_json = json.dumps(result)
            record.status = "COMPLETED"
            record.updated_at = datetime.utcnow()
            record.completed_at = datetime.utcnow()
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
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            }
    except Exception as exc:
        print(f"⚠ Failed reading record {job_id}: {exc}")
        return None
