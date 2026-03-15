"""
Database layer using SQLAlchemy ORM. Configuration-driven connection string;
switch to PostgreSQL by setting DATABASE_URL in .env.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.config import DATABASE_PATH, DATABASE_URL
from core.models import Base, Job


def _ensure_sqlite_path() -> None:
    """Ensure parent directory exists for SQLite file (when using default path)."""
    if DATABASE_URL.startswith("sqlite"):
        path = Path(DATABASE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    """Create or return the global engine. SQLite needs check_same_thread=False for some use cases."""
    kwargs = {}
    if DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 10}
    return create_engine(DATABASE_URL, **kwargs)


_engine = None


def get_engine_lazy():
    """Lazy singleton engine so config is loaded before engine creation."""
    global _engine
    if _engine is None:
        _ensure_sqlite_path()
        _engine = get_engine()
    return _engine


def init_db() -> None:
    """Create the jobs table if it does not exist."""
    _ensure_sqlite_path()
    engine = get_engine_lazy()
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    """Yield a database session with commit/rollback on exit."""
    engine = get_engine_lazy()
    SessionLocal = sessionmaker(engine, expire_on_commit=False, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_job(place_id: str, place_folder: str | None = None) -> int:
    """Insert a Pending job and return its ID."""
    init_db()
    with get_session() as session:
        job = Job(
            place_id=place_id,
            place_folder=place_folder or place_id,
            status="Pending",
            created_at=datetime.utcnow().isoformat(),
        )
        session.add(job)
        session.flush()
        return job.id


def get_job(job_id: int) -> dict | None:
    """Fetch a job by ID, or None if not found."""
    init_db()
    with get_session() as session:
        job = session.get(Job, job_id)
        return job.to_dict() if job else None


def update_job_status(
    job_id: int,
    status: str,
    report_path: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update job status and optionally report_path or error_message."""
    completed_at = datetime.utcnow().isoformat() if status in ("Completed", "Failed") else None
    init_db()
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = status
            if report_path is not None:
                job.report_path = report_path
            if error_message is not None:
                job.error_message = error_message
            if completed_at is not None:
                job.completed_at = completed_at


def get_recent_completed_job_for_place(place_id: str, within_hours: int = 24) -> dict | None:
    """Return the most recent completed job for this place_id with completed_at within the last N hours, or None."""
    init_db()
    cutoff = (datetime.utcnow() - timedelta(hours=within_hours)).isoformat()
    with get_session() as session:
        stmt = (
            select(Job)
            .where(Job.place_id == place_id, Job.status == "Completed", Job.completed_at >= cutoff)
            .order_by(Job.completed_at.desc())
            .limit(1)
        )
        job = session.execute(stmt).scalars().first()
        return job.to_dict() if job else None
