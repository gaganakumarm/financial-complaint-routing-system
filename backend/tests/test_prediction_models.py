"""Tests for model registry and immutable prediction persistence."""

from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.models import (
    Complaint,
    ComplaintCategory,
    Department,
    ModelType,
    ModelVersion,
    Prediction,
)


EXPECTED_TABLES = {
    "roles", "users", "complaint_categories", "departments", "complaints",
    "complaint_status_history", "model_versions", "predictions",
}


def test_prediction_metadata_contains_exactly_approved_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_model_type_values_and_database_enum() -> None:
    assert [item.value for item in ModelType] == [
        "tfidf_classifier", "embedding_classifier", "prompted_llm",
        "fine_tuned_llm", "hybrid",
    ]
    enum_type = ModelVersion.__table__.c.model_type.type
    assert enum_type.name == "model_type"
    assert enum_type.enums == [item.value for item in ModelType]


def test_model_version_schema() -> None:
    table = ModelVersion.__table__
    assert set(table.c.keys()) == {
        "id", "name", "version", "model_type", "base_model_name",
        "artifact_location", "configuration", "is_active", "is_approved",
        "created_at", "activated_at", "deactivated_at",
    }
    assert "updated_at" not in table.c
    assert table.c.id.primary_key and table.c.id.type.python_type is UUID
    assert table.c.name.type.length == 100 and table.c.name.nullable is False
    assert table.c.version.type.length == 50 and table.c.version.nullable is False
    assert table.c.base_model_name.type.length == 200
    assert isinstance(table.c.configuration.type, JSONB)
    assert table.c.configuration.default is None
    _assert_boolean_default(table.c.is_active, False)
    _assert_boolean_default(table.c.is_approved, False)
    _assert_timestamps(table, "created_at", "activated_at", "deactivated_at")
    assert _check_names(table) == {
        "ck_model_versions_name_not_blank",
        "ck_model_versions_version_not_blank",
        "ck_model_versions_active_requires_approval",
        "ck_model_versions_active_requires_activated_at",
        "ck_model_versions_activation_timestamps_order",
    }
    expected_indexes = {
        "uq_model_versions_name_version": ["name", "version"],
        "ix_model_versions_model_type": ["model_type"],
        "ix_model_versions_is_active": ["is_active"],
        "uq_model_versions_single_active": ["is_active"],
    }
    assert {index.name for index in table.indexes} == set(expected_indexes)
    for name, columns in expected_indexes.items():
        assert _index_columns(table, name) == columns
    assert _index(table, "uq_model_versions_name_version").unique is True
    active_index = _index(table, "uq_model_versions_single_active")
    assert active_index.unique is True
    predicate = active_index.dialect_options["postgresql"]["where"]
    assert str(predicate.compile(dialect=postgresql.dialect())) == "is_active = true"
    assert ModelVersion.predictions.property.back_populates == "model_version"
    assert "delete" not in ModelVersion.predictions.property.cascade


def test_prediction_schema() -> None:
    table = Prediction.__table__
    assert set(table.c.keys()) == {
        "id", "complaint_id", "model_version_id", "predicted_category_id",
        "predicted_department_id", "predicted_urgency", "confidence_score",
        "raw_output", "output_valid", "failure_code", "failure_message",
        "inference_latency_ms", "created_at",
    }
    assert "updated_at" not in table.c
    assert table.c.id.primary_key and table.c.id.type.python_type is UUID
    expected_foreign_keys = {
        "complaint_id": ("complaints.id", "fk_predictions_complaint_id"),
        "model_version_id": (
            "model_versions.id", "fk_predictions_model_version_id"
        ),
        "predicted_category_id": (
            "complaint_categories.id", "fk_predictions_predicted_category_id"
        ),
        "predicted_department_id": (
            "departments.id", "fk_predictions_predicted_department_id"
        ),
    }
    for column_name, (target, name) in expected_foreign_keys.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "RESTRICT"
        assert foreign_key.constraint.name == name
    assert table.c.predicted_urgency.type.name == "complaint_urgency"
    assert isinstance(table.c.confidence_score.type, Numeric)
    assert table.c.confidence_score.type.precision == 6
    assert table.c.confidence_score.type.scale == 5
    assert isinstance(table.c.raw_output.type, JSONB)
    assert table.c.raw_output.default is None
    _assert_boolean_default(table.c.output_valid, False)
    assert table.c.failure_code.type.length == 100
    _assert_timestamps(table, "created_at")
    assert _check_names(table) == {
        "ck_predictions_confidence_score_range",
        "ck_predictions_failure_code_not_blank",
        "ck_predictions_inference_latency_non_negative",
        "ck_predictions_failure_consistency",
    }
    expected_indexes = {
        "ix_predictions_complaint_id": ["complaint_id"],
        "ix_predictions_model_version_id": ["model_version_id"],
        "ix_predictions_predicted_category_id": ["predicted_category_id"],
        "ix_predictions_predicted_department_id": ["predicted_department_id"],
        "ix_predictions_complaint_created_at": ["complaint_id", "created_at"],
        "ix_predictions_model_version_created_at": [
            "model_version_id", "created_at"
        ],
    }
    assert {index.name for index in table.indexes} == set(expected_indexes)
    for name, columns in expected_indexes.items():
        assert _index_columns(table, name) == columns
    relationships = {
        Prediction.complaint: "predictions",
        Prediction.model_version: "predictions",
        Prediction.predicted_category: "predictions",
        Prediction.predicted_department: "predictions",
    }
    for relationship, back_populates in relationships.items():
        assert relationship.property.back_populates == back_populates
        assert "delete" not in relationship.property.cascade


def test_prediction_relationships_work_in_memory() -> None:
    complaint = Complaint(
        reference_number="CMP-PREDICTION", title="Example",
        description="Example complaint",
    )
    model_version = ModelVersion(
        name="financial-complaint-router", version="1.0.0",
        model_type=ModelType.TFIDF_CLASSIFIER,
    )
    category = ComplaintCategory(code="example", display_name="Example")
    department = Department(code="operations", display_name="Operations")
    prediction = Prediction(
        complaint=complaint,
        model_version=model_version,
        predicted_category=category,
        predicted_department=department,
    )
    assert prediction in complaint.predictions
    assert prediction in model_version.predictions
    assert prediction in category.predictions
    assert prediction in department.predictions
    assert Complaint.predictions.property.back_populates == "complaint"
    assert ComplaintCategory.predictions.property.back_populates == (
        "predicted_category"
    )
    assert Department.predictions.property.back_populates == "predicted_department"


def test_prediction_migration_operations(monkeypatch) -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = list(script.walk_revisions())
    assert [(item.revision, item.down_revision) for item in revisions] == [
        ("20260804_03", "20260804_02"),
        ("20260804_02", "20260803_01"),
        ("20260803_01", None),
    ]
    assert script.get_heads() == ["20260804_03"]
    module = revisions[0].module
    operations: list[tuple[str, str]] = []
    enum_operations: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(
        module._model_type, "create",
        lambda bind, checkfirst: enum_operations.append(("create", "model_type")),
    )
    monkeypatch.setattr(
        module._model_type, "drop",
        lambda bind, checkfirst: enum_operations.append(("drop", "model_type")),
    )
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(
            module.op, method,
            lambda name, *args, _method=method, **kwargs: operations.append(
                (_method, name)
            ),
        )
    module.upgrade()
    assert enum_operations == [("create", "model_type")]
    assert [value for operation, value in operations if operation == "create_table"] == [
        "model_versions", "predictions",
    ]
    assert {value for operation, value in operations if operation == "create_index"} == {
        "uq_model_versions_name_version", "ix_model_versions_model_type",
        "ix_model_versions_is_active", "uq_model_versions_single_active",
        "ix_predictions_complaint_id", "ix_predictions_model_version_id",
        "ix_predictions_predicted_category_id",
        "ix_predictions_predicted_department_id",
        "ix_predictions_complaint_created_at",
        "ix_predictions_model_version_created_at",
    }
    operations.clear()
    module.downgrade()
    assert [value for operation, value in operations if operation == "drop_table"] == [
        "predictions", "model_versions",
    ]
    assert enum_operations == [("create", "model_type"), ("drop", "model_type")]
    assert not any("complaint_urgency" in value for _, value in enum_operations)


def _assert_boolean_default(column, value: bool) -> None:
    assert column.default.arg is value
    assert str(column.server_default.arg).lower() == str(value).lower()


def _assert_timestamps(table, *names: str) -> None:
    for name in names:
        assert isinstance(table.c[name].type, DateTime)
        assert table.c[name].type.timezone is True


def _check_names(table) -> set[str]:
    return {
        constraint.name for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _index(table, name: str):
    return next(index for index in table.indexes if index.name == name)


def _index_columns(table, name: str) -> list[str]:
    return [column.name for column in _index(table, name).columns]
