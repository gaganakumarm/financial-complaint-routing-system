"""Benchmark experiment persistence model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_result import BenchmarkResult
    from app.models.dataset_version import DatasetVersion


class BenchmarkExperimentStatus(StrEnum):
    """Controlled benchmark execution states persisted as lowercase values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def benchmark_experiment_status_enum() -> Enum:
    """Build the native benchmark-experiment-status enum mapping."""
    return Enum(
        BenchmarkExperimentStatus,
        name="benchmark_experiment_status",
        values_callable=lambda members: [member.value for member in members],
    )


class BenchmarkExperiment(UUIDPrimaryKeyMixin, Base):
    """A controlled and reproducible benchmark execution record."""

    __tablename__ = "benchmark_experiments"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "dataset_versions.id",
            name="fk_benchmark_experiments_dataset_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[BenchmarkExperimentStatus] = mapped_column(
        benchmark_experiment_status_enum(),
        default=BenchmarkExperimentStatus.PENDING,
        server_default=BenchmarkExperimentStatus.PENDING.value,
        nullable=False,
    )
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "btrim(name) <> ''",
            name="ck_benchmark_experiments_name_not_blank",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_benchmark_experiments_timestamps_order",
        ),
        CheckConstraint(
            "status <> 'pending' OR "
            "(started_at IS NULL AND completed_at IS NULL AND failure_message IS NULL)",
            name="ck_benchmark_experiments_pending_consistency",
        ),
        CheckConstraint(
            "status <> 'running' OR "
            "(started_at IS NOT NULL AND completed_at IS NULL "
            "AND failure_message IS NULL)",
            name="ck_benchmark_experiments_running_requires_started_at",
        ),
        CheckConstraint(
            "status <> 'completed' OR "
            "(started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND failure_message IS NULL)",
            name="ck_benchmark_experiments_completed_requires_timestamps",
        ),
        CheckConstraint(
            "status <> 'failed' OR "
            "(started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_benchmark_experiments_failed_requires_completion",
        ),
        CheckConstraint(
            "(status = 'failed' OR failure_message IS NULL) AND "
            "(failure_message IS NULL OR btrim(failure_message) <> '')",
            name="ck_benchmark_experiments_failure_message_consistency",
        ),
        Index(
            "ix_benchmark_experiments_dataset_version_id",
            "dataset_version_id",
        ),
        Index("ix_benchmark_experiments_status", "status"),
        Index(
            "ix_benchmark_experiments_status_created_at",
            "status",
            "created_at",
        ),
    )

    dataset_version: Mapped[DatasetVersion] = relationship(
        back_populates="benchmark_experiments"
    )
    results: Mapped[list[BenchmarkResult]] = relationship(back_populates="experiment")
