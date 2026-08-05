"""Immutable benchmark-result persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_comparison import BenchmarkComparison
    from app.models.benchmark_comparison_member import BenchmarkComparisonMember
    from app.models.benchmark_example_result import BenchmarkExampleResult
    from app.models.benchmark_experiment import BenchmarkExperiment
    from app.models.model_version import ModelVersion
    from app.models.model_promotion_decision import ModelPromotionDecision
    from app.models.deployment_candidate import DeploymentCandidate


class BenchmarkResult(UUIDPrimaryKeyMixin, Base):
    """Immutable measured output for one model in one benchmark experiment."""

    __tablename__ = "benchmark_results"

    benchmark_experiment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "benchmark_experiments.id",
            name="fk_benchmark_results_experiment_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    model_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "model_versions.id",
            name="fk_benchmark_results_model_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    macro_precision: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    macro_recall: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    macro_f1: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    cost_weighted_error: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6), nullable=True
    )
    structured_output_validity_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 5), nullable=True
    )
    average_inference_latency_ms: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    throughput_per_second: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 6), nullable=True
    )
    per_class_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    additional_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_error_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    exact_match_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    failed_prediction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    department_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    urgency_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    p95_inference_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "sample_count > 0", name="ck_benchmark_results_sample_count_positive"
        ),
        CheckConstraint(
            "accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)",
            name="ck_benchmark_results_accuracy_range",
        ),
        CheckConstraint(
            "macro_precision IS NULL OR (macro_precision >= 0 AND macro_precision <= 1)",
            name="ck_benchmark_results_macro_precision_range",
        ),
        CheckConstraint(
            "macro_recall IS NULL OR (macro_recall >= 0 AND macro_recall <= 1)",
            name="ck_benchmark_results_macro_recall_range",
        ),
        CheckConstraint(
            "macro_f1 IS NULL OR (macro_f1 >= 0 AND macro_f1 <= 1)",
            name="ck_benchmark_results_macro_f1_range",
        ),
        CheckConstraint(
            "structured_output_validity_rate IS NULL OR "
            "(structured_output_validity_rate >= 0 "
            "AND structured_output_validity_rate <= 1)",
            name="ck_benchmark_results_validity_rate_range",
        ),
        CheckConstraint(
            "cost_weighted_error IS NULL OR cost_weighted_error >= 0",
            name="ck_benchmark_results_cost_weighted_error_non_negative",
        ),
        CheckConstraint(
            "average_inference_latency_ms IS NULL "
            "OR average_inference_latency_ms >= 0",
            name="ck_benchmark_results_latency_non_negative",
        ),
        CheckConstraint(
            "throughput_per_second IS NULL OR throughput_per_second >= 0",
            name="ck_benchmark_results_throughput_non_negative",
        ),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_benchmark_results_estimated_cost_non_negative",
        ),
        CheckConstraint("total_error_cost IS NULL OR total_error_cost >= 0", name="ck_benchmark_results_total_error_cost_non_negative"),
        CheckConstraint("failed_prediction_count IS NULL OR (failed_prediction_count >= 0 AND failed_prediction_count <= sample_count)", name="ck_benchmark_results_failed_prediction_count_range"),
        CheckConstraint("exact_match_accuracy IS NULL OR (exact_match_accuracy >= 0 AND exact_match_accuracy <= 1)", name="ck_benchmark_results_exact_match_accuracy_range"),
        CheckConstraint("category_accuracy IS NULL OR (category_accuracy >= 0 AND category_accuracy <= 1)", name="ck_benchmark_results_category_accuracy_range"),
        CheckConstraint("department_accuracy IS NULL OR (department_accuracy >= 0 AND department_accuracy <= 1)", name="ck_benchmark_results_department_accuracy_range"),
        CheckConstraint("urgency_accuracy IS NULL OR (urgency_accuracy >= 0 AND urgency_accuracy <= 1)", name="ck_benchmark_results_urgency_accuracy_range"),
        CheckConstraint("p95_inference_latency_ms IS NULL OR p95_inference_latency_ms >= 0", name="ck_benchmark_results_p95_latency_non_negative"),
        Index(
            "uq_benchmark_results_experiment_model",
            "benchmark_experiment_id",
            "model_version_id",
            unique=True,
        ),
        Index("ix_benchmark_results_experiment_id", "benchmark_experiment_id"),
        Index("ix_benchmark_results_model_version_id", "model_version_id"),
        Index(
            "ix_benchmark_results_model_created_at",
            "model_version_id",
            "created_at",
        ),
    )

    experiment: Mapped[BenchmarkExperiment] = relationship(back_populates="results")
    model_version: Mapped[ModelVersion] = relationship(
        back_populates="benchmark_results"
    )
    example_results: Mapped[list[BenchmarkExampleResult]] = relationship(back_populates="benchmark_result")
    comparison_members: Mapped[list[BenchmarkComparisonMember]] = relationship(back_populates="benchmark_result")
    winning_comparisons: Mapped[list[BenchmarkComparison]] = relationship(back_populates="winner_result", foreign_keys="BenchmarkComparison.winner_result_id")
    model_promotion_decisions: Mapped[list[ModelPromotionDecision]] = relationship(back_populates="selected_benchmark_result")
    deployment_candidates: Mapped[list[DeploymentCandidate]] = relationship(back_populates="benchmark_result")
