"""Create benchmark example results and type aggregate metrics.

Revision ID: 20260805_08
Revises: 20260805_07
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_08"
down_revision: str | None = "20260805_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_urgency = postgresql.ENUM("low", "medium", "high", "critical", name="complaint_urgency", create_type=False)


def upgrade() -> None:
    for column in (
        sa.Column("total_error_cost", sa.Numeric(14, 6), nullable=True), sa.Column("exact_match_accuracy", sa.Numeric(6, 5), nullable=True),
        sa.Column("failed_prediction_count", sa.Integer(), nullable=True), sa.Column("category_accuracy", sa.Numeric(6, 5), nullable=True),
        sa.Column("department_accuracy", sa.Numeric(6, 5), nullable=True), sa.Column("urgency_accuracy", sa.Numeric(6, 5), nullable=True),
        sa.Column("p95_inference_latency_ms", sa.Integer(), nullable=True),
    ): op.add_column("benchmark_results", column)
    checks = {
        "ck_benchmark_results_total_error_cost_non_negative": "total_error_cost IS NULL OR total_error_cost >= 0",
        "ck_benchmark_results_failed_prediction_count_range": "failed_prediction_count IS NULL OR (failed_prediction_count >= 0 AND failed_prediction_count <= sample_count)",
        "ck_benchmark_results_exact_match_accuracy_range": "exact_match_accuracy IS NULL OR (exact_match_accuracy >= 0 AND exact_match_accuracy <= 1)",
        "ck_benchmark_results_category_accuracy_range": "category_accuracy IS NULL OR (category_accuracy >= 0 AND category_accuracy <= 1)",
        "ck_benchmark_results_department_accuracy_range": "department_accuracy IS NULL OR (department_accuracy >= 0 AND department_accuracy <= 1)",
        "ck_benchmark_results_urgency_accuracy_range": "urgency_accuracy IS NULL OR (urgency_accuracy >= 0 AND urgency_accuracy <= 1)",
        "ck_benchmark_results_p95_latency_non_negative": "p95_inference_latency_ms IS NULL OR p95_inference_latency_ms >= 0",
    }
    for name, condition in checks.items(): op.create_check_constraint(name, "benchmark_results", condition)
    op.create_table("benchmark_example_results",
        sa.Column("benchmark_result_id", sa.Uuid(), nullable=False), sa.Column("dataset_example_id", sa.Uuid(), nullable=False),
        sa.Column("predicted_category_id", sa.Uuid(), nullable=True), sa.Column("predicted_department_id", sa.Uuid(), nullable=True),
        sa.Column("predicted_urgency", _urgency, nullable=True), sa.Column("confidence", sa.Numeric(6, 5), nullable=True),
        sa.Column("inference_latency_ms", sa.Integer(), nullable=True), sa.Column("prediction_succeeded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("structured_output_valid", sa.Boolean(), server_default=sa.false(), nullable=False), sa.Column("failure_code", sa.String(50), nullable=True),
        sa.Column("category_correct", sa.Boolean(), nullable=False), sa.Column("department_correct", sa.Boolean(), nullable=False), sa.Column("urgency_correct", sa.Boolean(), nullable=False),
        sa.Column("exact_match", sa.Boolean(), nullable=False), sa.Column("error_cost", sa.Numeric(8, 2), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("inference_latency_ms IS NULL OR inference_latency_ms >= 0", name="ck_benchmark_example_results_latency_non_negative"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_benchmark_example_results_confidence_range"),
        sa.CheckConstraint("error_cost >= 0", name="ck_benchmark_example_results_error_cost_non_negative"),
        sa.CheckConstraint("failure_code IS NULL OR btrim(failure_code) <> ''", name="ck_benchmark_example_results_failure_code_not_blank"),
        sa.CheckConstraint("NOT prediction_succeeded OR (predicted_category_id IS NOT NULL AND predicted_department_id IS NOT NULL AND predicted_urgency IS NOT NULL AND inference_latency_ms IS NOT NULL)", name="ck_benchmark_example_results_success_values"),
        sa.CheckConstraint("NOT prediction_succeeded OR failure_code IS NULL", name="ck_benchmark_example_results_success_no_failure"),
        sa.CheckConstraint("prediction_succeeded OR (failure_code IS NOT NULL AND btrim(failure_code) <> '' AND NOT category_correct AND NOT department_correct AND NOT urgency_correct AND NOT exact_match)", name="ck_benchmark_example_results_failure_consistency"),
        sa.CheckConstraint("NOT exact_match OR (category_correct AND department_correct AND urgency_correct)", name="ck_benchmark_example_results_exact_match_requires_all"),
        sa.CheckConstraint("(category_correct AND department_correct AND urgency_correct) OR NOT exact_match", name="ck_benchmark_example_results_mismatch_not_exact"),
        sa.CheckConstraint("prediction_succeeded OR NOT structured_output_valid", name="ck_benchmark_example_results_failed_output_invalid"),
        sa.ForeignKeyConstraint(["benchmark_result_id"], ["benchmark_results.id"], name="fk_benchmark_example_results_result_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_example_id"], ["dataset_examples.id"], name="fk_benchmark_example_results_example_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["predicted_category_id"], ["complaint_categories.id"], name="fk_benchmark_example_results_category_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["predicted_department_id"], ["departments.id"], name="fk_benchmark_example_results_department_id", ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"))
    for name, columns, unique in (
        ("uq_benchmark_example_results_result_example", ["benchmark_result_id", "dataset_example_id"], True), ("ix_benchmark_example_results_result_id", ["benchmark_result_id"], False),
        ("ix_benchmark_example_results_example_id", ["dataset_example_id"], False), ("ix_benchmark_example_results_prediction_succeeded", ["prediction_succeeded"], False),
        ("ix_benchmark_example_results_exact_match", ["exact_match"], False), ("ix_benchmark_example_results_failure_code", ["failure_code"], False),
    ): op.create_index(name, "benchmark_example_results", columns, unique=unique)

    op.add_column("benchmark_comparisons", sa.Column("winner_result_id", sa.Uuid(), nullable=True))
    op.add_column("benchmark_comparison_members", sa.Column("benchmark_result_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE benchmark_comparisons c SET winner_result_id = r.id FROM benchmark_results r WHERE r.benchmark_experiment_id = c.winner_experiment_id AND (SELECT count(*) FROM benchmark_results x WHERE x.benchmark_experiment_id = c.winner_experiment_id) = 1")
    op.execute("UPDATE benchmark_comparison_members m SET benchmark_result_id = r.id FROM benchmark_results r WHERE r.benchmark_experiment_id = m.benchmark_experiment_id AND (SELECT count(*) FROM benchmark_results x WHERE x.benchmark_experiment_id = m.benchmark_experiment_id) = 1")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM benchmark_comparisons WHERE winner_result_id IS NULL) OR EXISTS (SELECT 1 FROM benchmark_comparison_members WHERE benchmark_result_id IS NULL) THEN RAISE EXCEPTION 'ambiguous legacy benchmark comparison references require remediation'; END IF; END $$")
    op.alter_column("benchmark_comparisons", "winner_result_id", nullable=False)
    op.alter_column("benchmark_comparison_members", "benchmark_result_id", nullable=False)
    op.create_foreign_key("fk_benchmark_comparisons_winner_result_id", "benchmark_comparisons", "benchmark_results", ["winner_result_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_benchmark_comparison_members_result_id", "benchmark_comparison_members", "benchmark_results", ["benchmark_result_id"], ["id"], ondelete="RESTRICT")
    op.drop_index("ix_benchmark_comparisons_winner_experiment_id", table_name="benchmark_comparisons")
    op.drop_constraint("fk_benchmark_comparisons_winner_experiment_id", "benchmark_comparisons", type_="foreignkey")
    op.drop_column("benchmark_comparisons", "winner_experiment_id")
    op.drop_index("uq_benchmark_comparison_members_comparison_experiment", table_name="benchmark_comparison_members")
    op.drop_index("ix_benchmark_comparison_members_experiment_id", table_name="benchmark_comparison_members")
    op.drop_constraint("fk_benchmark_comparison_members_experiment_id", "benchmark_comparison_members", type_="foreignkey")
    op.drop_column("benchmark_comparison_members", "benchmark_experiment_id")
    op.create_index("ix_benchmark_comparisons_winner_result_id", "benchmark_comparisons", ["winner_result_id"])
    op.create_index("uq_benchmark_comparison_members_comparison_result", "benchmark_comparison_members", ["benchmark_comparison_id", "benchmark_result_id"], unique=True)
    op.create_index("ix_benchmark_comparison_members_result_id", "benchmark_comparison_members", ["benchmark_result_id"])


def downgrade() -> None:
    op.add_column("benchmark_comparisons", sa.Column("winner_experiment_id", sa.Uuid(), nullable=True))
    op.add_column("benchmark_comparison_members", sa.Column("benchmark_experiment_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE benchmark_comparisons c SET winner_experiment_id = r.benchmark_experiment_id FROM benchmark_results r WHERE r.id = c.winner_result_id")
    op.execute("UPDATE benchmark_comparison_members m SET benchmark_experiment_id = r.benchmark_experiment_id FROM benchmark_results r WHERE r.id = m.benchmark_result_id")
    op.alter_column("benchmark_comparisons", "winner_experiment_id", nullable=False); op.alter_column("benchmark_comparison_members", "benchmark_experiment_id", nullable=False)
    op.drop_index("ix_benchmark_comparison_members_result_id", table_name="benchmark_comparison_members"); op.drop_index("uq_benchmark_comparison_members_comparison_result", table_name="benchmark_comparison_members")
    op.drop_constraint("fk_benchmark_comparison_members_result_id", "benchmark_comparison_members", type_="foreignkey"); op.drop_column("benchmark_comparison_members", "benchmark_result_id")
    op.drop_index("ix_benchmark_comparisons_winner_result_id", table_name="benchmark_comparisons"); op.drop_constraint("fk_benchmark_comparisons_winner_result_id", "benchmark_comparisons", type_="foreignkey"); op.drop_column("benchmark_comparisons", "winner_result_id")
    op.create_foreign_key("fk_benchmark_comparisons_winner_experiment_id", "benchmark_comparisons", "benchmark_experiments", ["winner_experiment_id"], ["id"], ondelete="RESTRICT"); op.create_index("ix_benchmark_comparisons_winner_experiment_id", "benchmark_comparisons", ["winner_experiment_id"])
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM benchmark_comparison_members GROUP BY benchmark_comparison_id, benchmark_experiment_id HAVING count(*) > 1) THEN RAISE EXCEPTION 'benchmark comparison cannot be downgraded without merging result members'; END IF; END $$")
    op.create_foreign_key("fk_benchmark_comparison_members_experiment_id", "benchmark_comparison_members", "benchmark_experiments", ["benchmark_experiment_id"], ["id"], ondelete="RESTRICT"); op.create_index("uq_benchmark_comparison_members_comparison_experiment", "benchmark_comparison_members", ["benchmark_comparison_id", "benchmark_experiment_id"], unique=True); op.create_index("ix_benchmark_comparison_members_experiment_id", "benchmark_comparison_members", ["benchmark_experiment_id"])
    for name in ("ix_benchmark_example_results_failure_code", "ix_benchmark_example_results_exact_match", "ix_benchmark_example_results_prediction_succeeded", "ix_benchmark_example_results_example_id", "ix_benchmark_example_results_result_id", "uq_benchmark_example_results_result_example"): op.drop_index(name, table_name="benchmark_example_results")
    op.drop_table("benchmark_example_results")
    for name in ("ck_benchmark_results_p95_latency_non_negative", "ck_benchmark_results_urgency_accuracy_range", "ck_benchmark_results_department_accuracy_range", "ck_benchmark_results_category_accuracy_range", "ck_benchmark_results_exact_match_accuracy_range", "ck_benchmark_results_failed_prediction_count_range", "ck_benchmark_results_total_error_cost_non_negative"): op.drop_constraint(name, "benchmark_results", type_="check")
    for name in ("p95_inference_latency_ms", "urgency_accuracy", "department_accuracy", "category_accuracy", "failed_prediction_count", "exact_match_accuracy", "total_error_cost"): op.drop_column("benchmark_results", name)
