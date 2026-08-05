"""Membership rows for persisted benchmark comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_comparison import BenchmarkComparison
    from app.models.benchmark_result import BenchmarkResult


class BenchmarkComparisonMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "benchmark_comparison_members"

    benchmark_comparison_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("benchmark_comparisons.id", name="fk_benchmark_comparison_members_comparison_id", ondelete="CASCADE"), nullable=False)
    benchmark_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("benchmark_results.id", name="fk_benchmark_comparison_members_result_id", ondelete="RESTRICT"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("rank >= 1", name="ck_benchmark_comparison_members_rank_positive"),
        Index("uq_benchmark_comparison_members_comparison_result", "benchmark_comparison_id", "benchmark_result_id", unique=True),
        Index("uq_benchmark_comparison_members_comparison_rank", "benchmark_comparison_id", "rank", unique=True),
        Index("ix_benchmark_comparison_members_comparison_id", "benchmark_comparison_id"),
        Index("ix_benchmark_comparison_members_result_id", "benchmark_result_id"),
        Index("ix_benchmark_comparison_members_rank", "rank"),
    )

    comparison: Mapped[BenchmarkComparison] = relationship(back_populates="members")
    benchmark_result: Mapped[BenchmarkResult] = relationship(back_populates="comparison_members")
