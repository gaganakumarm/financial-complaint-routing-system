"""Auditable per-example outcomes for a benchmark result."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.complaint import ComplaintUrgency, complaint_urgency_enum

if TYPE_CHECKING:
    from app.models.benchmark_result import BenchmarkResult
    from app.models.complaint_category import ComplaintCategory
    from app.models.dataset_example import DatasetExample
    from app.models.department import Department


class BenchmarkExampleResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "benchmark_example_results"
    benchmark_result_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("benchmark_results.id", name="fk_benchmark_example_results_result_id", ondelete="CASCADE"), nullable=False)
    dataset_example_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dataset_examples.id", name="fk_benchmark_example_results_example_id", ondelete="RESTRICT"), nullable=False)
    predicted_category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("complaint_categories.id", name="fk_benchmark_example_results_category_id", ondelete="RESTRICT"), nullable=True)
    predicted_department_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", name="fk_benchmark_example_results_department_id", ondelete="RESTRICT"), nullable=True)
    predicted_urgency: Mapped[ComplaintUrgency | None] = mapped_column(complaint_urgency_enum(), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    inference_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_succeeded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    structured_output_valid: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    department_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    urgency_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exact_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_cost: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("inference_latency_ms IS NULL OR inference_latency_ms >= 0", name="ck_benchmark_example_results_latency_non_negative"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_benchmark_example_results_confidence_range"),
        CheckConstraint("error_cost >= 0", name="ck_benchmark_example_results_error_cost_non_negative"),
        CheckConstraint("failure_code IS NULL OR btrim(failure_code) <> ''", name="ck_benchmark_example_results_failure_code_not_blank"),
        CheckConstraint("NOT prediction_succeeded OR (predicted_category_id IS NOT NULL AND predicted_department_id IS NOT NULL AND predicted_urgency IS NOT NULL AND inference_latency_ms IS NOT NULL)", name="ck_benchmark_example_results_success_values"),
        CheckConstraint("NOT prediction_succeeded OR failure_code IS NULL", name="ck_benchmark_example_results_success_no_failure"),
        CheckConstraint("prediction_succeeded OR (failure_code IS NOT NULL AND btrim(failure_code) <> '' AND NOT category_correct AND NOT department_correct AND NOT urgency_correct AND NOT exact_match)", name="ck_benchmark_example_results_failure_consistency"),
        CheckConstraint("NOT exact_match OR (category_correct AND department_correct AND urgency_correct)", name="ck_benchmark_example_results_exact_match_requires_all"),
        CheckConstraint("(category_correct AND department_correct AND urgency_correct) OR NOT exact_match", name="ck_benchmark_example_results_mismatch_not_exact"),
        CheckConstraint("prediction_succeeded OR NOT structured_output_valid", name="ck_benchmark_example_results_failed_output_invalid"),
        Index("uq_benchmark_example_results_result_example", "benchmark_result_id", "dataset_example_id", unique=True),
        Index("ix_benchmark_example_results_result_id", "benchmark_result_id"), Index("ix_benchmark_example_results_example_id", "dataset_example_id"),
        Index("ix_benchmark_example_results_prediction_succeeded", "prediction_succeeded"), Index("ix_benchmark_example_results_exact_match", "exact_match"), Index("ix_benchmark_example_results_failure_code", "failure_code"),
    )
    benchmark_result: Mapped[BenchmarkResult] = relationship(back_populates="example_results")
    dataset_example: Mapped[DatasetExample] = relationship(back_populates="benchmark_example_results")
    predicted_category: Mapped[ComplaintCategory | None] = relationship()
    predicted_department: Mapped[Department | None] = relationship()
