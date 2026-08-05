"""Tests for the complaint lifecycle persistence schema."""

from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime

from app.db.base import Base
from app.models import (
    Complaint,
    ComplaintCategory,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintStatusHistory,
    ComplaintUrgency,
    Department,
    User,
)


EXPECTED_TABLES = {
    "roles",
    "users",
    "complaint_categories",
    "departments",
    "complaints",
    "complaint_status_history",
    "model_versions",
    "predictions",
    "reviews",
    "dataset_versions",
    "dataset_examples",
    "benchmark_experiments",
    "benchmark_results",
    "benchmark_comparisons",
    "benchmark_comparison_members",
}


def test_complaint_domain_metadata() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_complaint_category_schema() -> None:
    table = ComplaintCategory.__table__
    assert set(table.c.keys()) == {
        "id", "code", "display_name", "description", "is_high_risk",
        "is_active", "created_at", "updated_at",
    }
    assert table.c.id.primary_key and table.c.id.type.python_type is UUID
    assert table.c.code.type.length == 50 and table.c.code.nullable is False
    assert table.c.display_name.type.length == 100
    assert table.c.description.nullable is True
    _assert_boolean_default(table.c.is_high_risk, False, "false")
    _assert_boolean_default(table.c.is_active, True, "true")
    _assert_timestamp_columns(table, "created_at", "updated_at")
    assert _index_columns(table, "uq_complaint_categories_code") == ["code"]
    assert _index(table, "uq_complaint_categories_code").unique is True
    assert _check_names(table) == {
        "ck_complaint_categories_code_not_blank",
        "ck_complaint_categories_display_name_not_blank",
    }
    assert ComplaintCategory.complaints.property.back_populates == "final_category"
    assert "delete" not in ComplaintCategory.complaints.property.cascade


def test_department_schema() -> None:
    table = Department.__table__
    assert set(table.c.keys()) == {
        "id", "code", "display_name", "description", "is_active",
        "created_at", "updated_at",
    }
    assert "email" not in table.c
    assert table.c.code.type.length == 50 and table.c.code.nullable is False
    assert table.c.display_name.type.length == 100
    assert table.c.description.nullable is True
    _assert_boolean_default(table.c.is_active, True, "true")
    _assert_timestamp_columns(table, "created_at", "updated_at")
    assert _index_columns(table, "uq_departments_code") == ["code"]
    assert _index(table, "uq_departments_code").unique is True
    assert _check_names(table) == {
        "ck_departments_code_not_blank",
        "ck_departments_display_name_not_blank",
    }
    assert Department.complaints.property.back_populates == "final_department"
    assert "delete" not in Department.complaints.property.cascade


def test_complaint_enums_use_exact_lowercase_database_values() -> None:
    assert [item.value for item in ComplaintStatus] == [
        "submitted", "prediction_pending", "prediction_completed",
        "awaiting_review", "under_review", "routed", "closed",
        "prediction_failed",
    ]
    assert [item.value for item in ComplaintUrgency] == [
        "low", "medium", "high", "critical",
    ]
    assert [item.value for item in ComplaintChangeSource] == [
        "customer", "reviewer", "administrator", "system", "model_pipeline",
    ]
    assert Complaint.__table__.c.current_status.type.name == "complaint_status"
    assert Complaint.__table__.c.current_status.type.enums == [
        item.value for item in ComplaintStatus
    ]
    assert Complaint.__table__.c.final_urgency.type.name == "complaint_urgency"
    assert Complaint.__table__.c.final_urgency.type.enums == [
        item.value for item in ComplaintUrgency
    ]
    history = ComplaintStatusHistory.__table__
    assert history.c.change_source.type.name == "complaint_change_source"
    assert history.c.change_source.type.enums == [
        item.value for item in ComplaintChangeSource
    ]
    assert history.c.previous_status.type.name == "complaint_status"
    assert history.c.new_status.type.name == "complaint_status"


def test_complaint_schema() -> None:
    table = Complaint.__table__
    assert set(table.c.keys()) == {
        "id", "reference_number", "customer_id", "title", "description",
        "current_status", "final_category_id", "final_department_id",
        "final_urgency", "review_started_at", "review_completed_at",
        "created_at", "updated_at",
    }
    for forbidden in ("priority", "tracking_number", "assigned_to_user_id", "submitted_at"):
        assert forbidden not in table.c
    assert table.c.id.primary_key and table.c.id.type.python_type is UUID
    assert table.c.reference_number.type.length == 50
    assert table.c.title.type.length == 200
    assert table.c.description.nullable is False
    assert table.c.current_status.default.arg is ComplaintStatus.SUBMITTED
    assert str(table.c.current_status.server_default.arg) == "submitted"
    assert table.c.final_category_id.nullable is True
    assert table.c.final_department_id.nullable is True
    assert table.c.final_urgency.nullable is True
    _assert_timestamp_columns(
        table, "created_at", "updated_at", "review_started_at", "review_completed_at"
    )

    expected_foreign_keys = {
        "customer_id": ("users.id", "fk_complaints_customer_id"),
        "final_category_id": (
            "complaint_categories.id", "fk_complaints_final_category_id"
        ),
        "final_department_id": (
            "departments.id", "fk_complaints_final_department_id"
        ),
    }
    for column_name, (target, constraint_name) in expected_foreign_keys.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "RESTRICT"
        assert foreign_key.constraint.name == constraint_name

    expected_indexes = {
        "uq_complaints_reference_number": ["reference_number"],
        "ix_complaints_customer_id": ["customer_id"],
        "ix_complaints_customer_created_at": ["customer_id", "created_at"],
        "ix_complaints_review_queue": ["current_status", "created_at"],
        "ix_complaints_final_category_id": ["final_category_id"],
        "ix_complaints_final_department_id": ["final_department_id"],
    }
    assert {index.name for index in table.indexes} == set(expected_indexes)
    for name, columns in expected_indexes.items():
        assert _index_columns(table, name) == columns
    assert _index(table, "uq_complaints_reference_number").unique is True
    assert _check_names(table) == {
        "ck_complaints_reference_number_not_blank",
        "ck_complaints_title_not_blank",
        "ck_complaints_description_not_blank",
        "ck_complaints_review_timestamps_order",
        "ck_complaints_routed_requires_final_routing",
    }


def test_status_history_schema_and_relationships() -> None:
    table = ComplaintStatusHistory.__table__
    assert set(table.c.keys()) == {
        "id", "complaint_id", "previous_status", "new_status",
        "changed_by_user_id", "change_source", "reason", "created_at",
    }
    assert "updated_at" not in table.c
    assert table.c.previous_status.nullable is True
    assert table.c.new_status.nullable is False
    assert table.c.changed_by_user_id.nullable is True
    _assert_timestamp_columns(table, "created_at")
    assert table.c.created_at.default is not None

    expected_foreign_keys = {
        "complaint_id": (
            "complaints.id", "fk_complaint_status_history_complaint_id"
        ),
        "changed_by_user_id": (
            "users.id", "fk_complaint_status_history_changed_by_user_id"
        ),
    }
    for column_name, (target, name) in expected_foreign_keys.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "RESTRICT"
        assert foreign_key.constraint.name == name
    assert _index_columns(
        table, "ix_complaint_status_history_complaint_created_at"
    ) == ["complaint_id", "created_at"]
    assert _index_columns(
        table, "ix_complaint_status_history_changed_by_user_id"
    ) == ["changed_by_user_id"]
    assert Complaint.status_history.property.back_populates == "complaint"
    assert ComplaintStatusHistory.complaint.property.back_populates == "status_history"
    assert ComplaintStatusHistory.changed_by_user.property.back_populates == (
        "complaint_status_changes"
    )
    assert "delete" not in Complaint.status_history.property.cascade


def test_complaint_domain_relationships_work_in_memory() -> None:
    user = User(email="customer@example.com", password_hash="hash", full_name="Customer")
    category = ComplaintCategory(code="failed_transfer", display_name="Failed Transfer")
    department = Department(code="payments", display_name="Payments")
    complaint = Complaint(
        customer=user,
        final_category=category,
        final_department=department,
        reference_number="CMP-EXAMPLE",
        title="Transfer failed",
        description="A transfer did not complete.",
    )
    history = ComplaintStatusHistory(
        complaint=complaint,
        changed_by_user=user,
        new_status=ComplaintStatus.SUBMITTED,
        change_source=ComplaintChangeSource.CUSTOMER,
    )
    assert complaint in user.submitted_complaints
    assert complaint in category.complaints
    assert complaint in department.complaints
    assert history in complaint.status_history
    assert history in user.complaint_status_changes
    assert User.submitted_complaints.property.back_populates == "customer"
    assert User.complaint_status_changes.property.back_populates == "changed_by_user"
    assert not hasattr(User, "assigned_complaints")


def test_complaint_domain_migration_operations(monkeypatch) -> None:
    revision = ScriptDirectory.from_config(Config("alembic.ini")).get_revision(
        "20260804_02"
    )
    assert revision is not None and revision.down_revision == "20260803_01"
    module = revision.module
    operations: list[tuple[str, str]] = []
    enum_operations: list[tuple[str, str]] = []

    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    for enum_object in (
        module._complaint_status,
        module._complaint_urgency,
        module._complaint_change_source,
    ):
        monkeypatch.setattr(
            enum_object,
            "create",
            lambda bind, checkfirst, name=enum_object.name: enum_operations.append(
                ("create_enum", name)
            ),
        )
        monkeypatch.setattr(
            enum_object,
            "drop",
            lambda bind, checkfirst, name=enum_object.name: enum_operations.append(
                ("drop_enum", name)
            ),
        )
    monkeypatch.setattr(
        module.op, "create_table",
        lambda name, *args, **kwargs: operations.append(("create_table", name)),
    )
    monkeypatch.setattr(
        module.op, "create_index",
        lambda name, *args, **kwargs: operations.append(("create_index", name)),
    )
    monkeypatch.setattr(
        module.op, "drop_index",
        lambda name, *args, **kwargs: operations.append(("drop_index", name)),
    )
    monkeypatch.setattr(
        module.op, "drop_table",
        lambda name, *args, **kwargs: operations.append(("drop_table", name)),
    )

    module.upgrade()
    assert enum_operations == [
        ("create_enum", "complaint_status"),
        ("create_enum", "complaint_urgency"),
        ("create_enum", "complaint_change_source"),
    ]
    assert [value for operation, value in operations if operation == "create_table"] == [
        "complaint_categories", "departments", "complaints",
        "complaint_status_history",
    ]
    assert {value for operation, value in operations if operation == "create_index"} == {
        "uq_complaint_categories_code", "uq_departments_code",
        "uq_complaints_reference_number", "ix_complaints_customer_id",
        "ix_complaints_customer_created_at", "ix_complaints_review_queue",
        "ix_complaints_final_category_id", "ix_complaints_final_department_id",
        "ix_complaint_status_history_complaint_created_at",
        "ix_complaint_status_history_changed_by_user_id",
    }

    operations.clear()
    enum_operations.clear()
    module.downgrade()
    assert [value for operation, value in operations if operation == "drop_table"] == [
        "complaint_status_history", "complaints", "departments",
        "complaint_categories",
    ]
    assert enum_operations == [
        ("drop_enum", "complaint_change_source"),
        ("drop_enum", "complaint_urgency"),
        ("drop_enum", "complaint_status"),
    ]


def _assert_boolean_default(column, python_value: bool, server_value: str) -> None:
    assert column.nullable is False
    assert column.default.arg is python_value
    assert str(column.server_default.arg).lower() == server_value


def _assert_timestamp_columns(table, *names: str) -> None:
    for name in names:
        assert isinstance(table.c[name].type, DateTime)
        assert table.c[name].type.timezone is True


def _index(table, name: str):
    return next(index for index in table.indexes if index.name == name)


def _index_columns(table, name: str) -> list[str]:
    return [column.name for column in _index(table, name).columns]


def _check_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
