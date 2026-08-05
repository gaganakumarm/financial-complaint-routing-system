"""Tests for human-review persistence."""

from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime

from app.db.base import Base
from app.models import (
    Complaint,
    ComplaintCategory,
    Department,
    ModelType,
    ModelVersion,
    Prediction,
    Review,
    ReviewOutcome,
    User,
)


EXPECTED_TABLES = {
    "roles", "users", "complaint_categories", "departments", "complaints",
    "complaint_status_history", "model_versions", "predictions", "reviews",
    "deployment_candidate_status_history",
    "dataset_versions",
    "dataset_examples", "benchmark_experiments", "benchmark_results",
    "benchmark_comparisons", "benchmark_comparison_members",
    "benchmark_example_results",
    "model_promotion_decisions",
    "deployment_candidates",
}


def test_review_metadata_contains_exactly_approved_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_review_outcome_values_and_database_enum() -> None:
    assert list(ReviewOutcome) == [
        ReviewOutcome.PENDING,
        ReviewOutcome.APPROVED,
        ReviewOutcome.CORRECTED,
        ReviewOutcome.REJECTED,
    ]
    assert [item.value for item in ReviewOutcome] == [
        "pending", "approved", "corrected", "rejected",
    ]
    enum_type = Review.__table__.c.outcome.type
    assert enum_type.name == "review_outcome"
    assert enum_type.enums == [item.value for item in ReviewOutcome]


def test_review_schema() -> None:
    table = Review.__table__
    assert set(table.c.keys()) == {
        "id", "complaint_id", "prediction_id", "reviewer_id", "outcome",
        "approved_category_id", "approved_department_id", "approved_urgency",
        "comments", "started_at", "completed_at", "created_at",
    }
    assert "updated_at" not in table.c
    assert table.c.id.primary_key and table.c.id.type.python_type is UUID
    assert table.c.complaint_id.nullable is False
    assert table.c.prediction_id.nullable is False
    assert table.c.reviewer_id.nullable is False
    assert table.c.approved_category_id.nullable is True
    assert table.c.approved_department_id.nullable is True
    assert table.c.approved_urgency.nullable is True
    assert table.c.comments.nullable is True
    assert table.c.outcome.default.arg is ReviewOutcome.PENDING
    assert str(table.c.outcome.server_default.arg) == "pending"
    assert table.c.approved_urgency.type.name == "complaint_urgency"
    for name in ("started_at", "completed_at", "created_at"):
        assert isinstance(table.c[name].type, DateTime)
        assert table.c[name].type.timezone is True
    assert table.c.created_at.nullable is False
    assert table.c.created_at.default is not None

    expected_foreign_keys = {
        "complaint_id": ("complaints.id", "fk_reviews_complaint_id"),
        "prediction_id": ("predictions.id", "fk_reviews_prediction_id"),
        "reviewer_id": ("users.id", "fk_reviews_reviewer_id"),
        "approved_category_id": (
            "complaint_categories.id", "fk_reviews_approved_category_id"
        ),
        "approved_department_id": (
            "departments.id", "fk_reviews_approved_department_id"
        ),
    }
    for column_name, (target, constraint_name) in expected_foreign_keys.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "RESTRICT"
        assert foreign_key.constraint.name == constraint_name

    expected_indexes = {
        "uq_reviews_prediction_id": ["prediction_id"],
        "ix_reviews_complaint_id": ["complaint_id"],
        "ix_reviews_reviewer_id": ["reviewer_id"],
        "ix_reviews_approved_category_id": ["approved_category_id"],
        "ix_reviews_approved_department_id": ["approved_department_id"],
        "ix_reviews_outcome_created_at": ["outcome", "created_at"],
        "ix_reviews_reviewer_created_at": ["reviewer_id", "created_at"],
    }
    assert {index.name for index in table.indexes} == set(expected_indexes)
    for name, columns in expected_indexes.items():
        assert _index_columns(table, name) == columns
    assert _index(table, "uq_reviews_prediction_id").unique is True
    assert _check_names(table) == {
        "ck_reviews_completion_timestamps_order",
        "ck_reviews_pending_consistency",
        "ck_reviews_completed_outcome_requires_completed_at",
        "ck_reviews_approved_requires_routing",
        "ck_reviews_corrected_requires_routing",
        "ck_reviews_rejected_has_no_routing",
    }


def test_review_relationships_are_symmetric_without_delete_cascade() -> None:
    relationships = [
        (Complaint.reviews, "complaint"),
        (Review.complaint, "reviews"),
        (Prediction.review, "prediction"),
        (Review.prediction, "review"),
        (User.reviews_performed, "reviewer"),
        (Review.reviewer, "reviews_performed"),
        (ComplaintCategory.approved_reviews, "approved_category"),
        (Review.approved_category, "approved_reviews"),
        (Department.approved_reviews, "approved_department"),
        (Review.approved_department, "approved_reviews"),
    ]
    for relationship, back_populates in relationships:
        assert relationship.property.back_populates == back_populates
        assert "delete" not in relationship.property.cascade
    assert Prediction.review.property.uselist is False
    assert Review.prediction.property.uselist is False


def test_review_relationships_work_in_memory() -> None:
    user = User(email="reviewer@example.com", password_hash="hash", full_name="Reviewer")
    complaint = Complaint(
        reference_number="CMP-REVIEW", title="Example", description="Example complaint"
    )
    model_version = ModelVersion(
        name="router", version="1.0.0", model_type=ModelType.TFIDF_CLASSIFIER
    )
    prediction = Prediction(complaint=complaint, model_version=model_version)
    category = ComplaintCategory(code="example", display_name="Example")
    department = Department(code="operations", display_name="Operations")
    review = Review(
        complaint=complaint,
        prediction=prediction,
        reviewer=user,
        approved_category=category,
        approved_department=department,
    )
    assert review in complaint.reviews
    assert prediction.review is review
    assert review in user.reviews_performed
    assert review in category.approved_reviews
    assert review in department.approved_reviews


def test_review_migration_operations(monkeypatch) -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = list(script.walk_revisions())
    assert [(item.revision, item.down_revision) for item in revisions] == [
        ("20260805_11", "20260805_10"),
        ("20260805_10", "20260805_09"),
        ("20260805_09", "20260805_08"),
        ("20260805_08", "20260805_07"),
        ("20260805_07", "20260805_06"),
        ("20260805_06", "20260804_05"),
        ("20260804_05", "20260804_04"),
        ("20260804_04", "20260804_03"),
        ("20260804_03", "20260804_02"),
        ("20260804_02", "20260803_01"),
        ("20260803_01", None),
    ]
    assert script.get_heads() == ["20260805_11"]
    module = revisions[7].module
    operations: list[tuple[str, str]] = []
    enum_operations: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(
        module._review_outcome,
        "create",
        lambda bind, checkfirst: enum_operations.append(("create", "review_outcome")),
    )
    monkeypatch.setattr(
        module._review_outcome,
        "drop",
        lambda bind, checkfirst: enum_operations.append(("drop", "review_outcome")),
    )
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(
            module.op,
            method,
            lambda name, *args, _method=method, **kwargs: operations.append(
                (_method, name)
            ),
        )
    module.upgrade()
    assert enum_operations == [("create", "review_outcome")]
    assert [value for operation, value in operations if operation == "create_table"] == [
        "reviews"
    ]
    assert {value for operation, value in operations if operation == "create_index"} == {
        "uq_reviews_prediction_id", "ix_reviews_complaint_id",
        "ix_reviews_reviewer_id", "ix_reviews_approved_category_id",
        "ix_reviews_approved_department_id", "ix_reviews_outcome_created_at",
        "ix_reviews_reviewer_created_at",
    }
    operations.clear()
    module.downgrade()
    assert [value for operation, value in operations if operation == "drop_table"] == [
        "reviews"
    ]
    assert enum_operations == [
        ("create", "review_outcome"), ("drop", "review_outcome")
    ]
    assert not any("complaint_urgency" in value for _, value in enum_operations)


def _check_names(table) -> set[str]:
    return {
        constraint.name for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _index(table, name: str):
    return next(index for index in table.indexes if index.name == name)


def _index_columns(table, name: str) -> list[str]:
    return [column.name for column in _index(table, name).columns]
