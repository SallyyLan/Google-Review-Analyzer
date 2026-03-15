"""
SQLAlchemy models for the job queue. Used by db.py for all persistence.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all models."""


class Job(Base):
    """Analysis job: one place_id per job, status and report path."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[str] = mapped_column(String(512), nullable=False)
    place_folder: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="Pending")
    report_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def to_dict(self) -> dict:
        """Return a dict compatible with the previous raw-SQL row interface."""
        return {
            "id": self.id,
            "place_id": self.place_id,
            "place_folder": self.place_folder,
            "status": self.status,
            "report_path": self.report_path,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
