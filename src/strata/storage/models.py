"""SQLAlchemy models for SQLite run metadata storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for Strata persistence models."""
    pass


class RunRecord(Base):
    """Persistent database record representing an experiment run."""

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    events_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    final_virtual_time_us: Mapped[int] = mapped_column(Integer, nullable=False)
    wall_clock_duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    all_invariants_passed: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 or 1
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    invariant_records: Mapped[list[InvariantRecord]] = relationship(
        "InvariantRecord",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class InvariantRecord(Base):
    """Persistent record of an evaluated invariant."""

    __tablename__ = "invariant_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True, nullable=False)
    invariant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    invariant_type: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[RunRecord] = relationship("RunRecord", back_populates="invariant_records")
