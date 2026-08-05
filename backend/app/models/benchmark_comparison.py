"""Persisted deterministic benchmark comparisons."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.benchmark_comparison_member import BenchmarkComparisonMember
    from app.models.benchmark_result import BenchmarkResult
    from app.models.dataset_version import DatasetVersion
    from app.models.user import User
    from app.models.model_promotion_decision import ModelPromotionDecision


class BenchmarkComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable snapshot of a ranked benchmark comparison."""

    __tablename__ = "benchmark_comparisons"

    dataset_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dataset_versions.id", name="fk_benchmark_comparisons_dataset_version_id", ondelete="RESTRICT"), nullable=False)
    dataset_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_example_count: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("benchmark_results.id", name="fk_benchmark_comparisons_winner_result_id", ondelete="RESTRICT"), nullable=False)
    ranking_metric: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", name="fk_benchmark_comparisons_created_by_user_id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("btrim(dataset_checksum) <> ''", name="ck_benchmark_comparisons_dataset_checksum_not_blank"),
        CheckConstraint("dataset_example_count > 0", name="ck_benchmark_comparisons_example_count_positive"),
        CheckConstraint("btrim(ranking_metric) <> ''", name="ck_benchmark_comparisons_ranking_metric_not_blank"),
        Index("ix_benchmark_comparisons_dataset_version_id", "dataset_version_id"),
        Index("ix_benchmark_comparisons_winner_result_id", "winner_result_id"),
        Index("ix_benchmark_comparisons_created_by_user_id", "created_by_user_id"),
        Index("ix_benchmark_comparisons_created_at", "created_at"),
    )

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="benchmark_comparisons")
    winner_result: Mapped[BenchmarkResult] = relationship(back_populates="winning_comparisons", foreign_keys=[winner_result_id])
    created_by_user: Mapped[User] = relationship(back_populates="created_benchmark_comparisons", foreign_keys=[created_by_user_id])
    members: Mapped[list[BenchmarkComparisonMember]] = relationship(back_populates="comparison")
    model_promotion_decisions: Mapped[list[ModelPromotionDecision]] = relationship(back_populates="benchmark_comparison")
