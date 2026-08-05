"""Dataset example model and migration tests."""
from alembic.config import Config
from alembic.script import ScriptDirectory
from unittest.mock import MagicMock
from uuid import uuid4
from sqlalchemy import CheckConstraint, DateTime, String, Text, Uuid
from app.models import ComplaintCategory, ComplaintUrgency, DatasetExample, DatasetVersion, Department


def test_dataset_example_metadata_contract() -> None:
    table = DatasetExample.__table__
    assert set(table.c) == {table.c.id, table.c.dataset_version_id, table.c.example_id, table.c.title, table.c.description, table.c.expected_category_id, table.c.expected_department_id, table.c.expected_urgency, table.c.created_at}
    assert table.c.title.type.length == 200
    assert table.c.expected_urgency.type.name == "complaint_urgency"
    assert all(not column.nullable for column in table.c)
    assert {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)} == {"ck_dataset_examples_example_id_not_blank", "ck_dataset_examples_title_not_blank", "ck_dataset_examples_description_not_blank"}
    assert {index.name for index in table.indexes} == {"uq_dataset_examples_dataset_example_id", "ix_dataset_examples_dataset_version_id", "ix_dataset_examples_expected_category_id", "ix_dataset_examples_expected_department_id"}


def test_dataset_example_migration_is_current_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260805_08"]
    assert script.get_revision("20260805_06").down_revision == "20260804_05"


def test_exact_columns_primary_key_foreign_keys_and_delete_policy() -> None:
    table = DatasetExample.__table__
    assert table.name == "dataset_examples"
    assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
    assert isinstance(table.c.dataset_version_id.type, Uuid)
    assert isinstance(table.c.example_id.type, String) and table.c.example_id.type.length == 200
    assert isinstance(table.c.title.type, String) and table.c.title.type.length == 200
    assert isinstance(table.c.description.type, Text)
    assert isinstance(table.c.created_at.type, DateTime) and table.c.created_at.type.timezone
    expected = {"dataset_version_id": "dataset_versions.id", "expected_category_id": "complaint_categories.id", "expected_department_id": "departments.id"}
    for column, target in expected.items():
        foreign_key = next(iter(table.c[column].foreign_keys))
        assert foreign_key.target_fullname == target and foreign_key.ondelete == "RESTRICT"


def test_relationships_are_reciprocal_and_work_in_memory() -> None:
    dataset, category, department = DatasetVersion(), ComplaintCategory(), Department()
    example = DatasetExample(id=uuid4(), dataset_version=dataset, expected_category=category, expected_department=department, example_id="one", title="title", description="description", expected_urgency=ComplaintUrgency.HIGH)
    assert example in dataset.examples
    assert example in category.dataset_examples
    assert example in department.dataset_examples
    assert DatasetExample.dataset_version.property.back_populates == "examples"
    assert DatasetExample.expected_category.property.back_populates == "dataset_examples"
    assert DatasetExample.expected_department.property.back_populates == "dataset_examples"


def test_migration_upgrade_and_downgrade_do_not_manage_shared_enum(monkeypatch) -> None:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260805_06").module
    operations = []
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name, kwargs)))
    module.upgrade()
    assert [name for operation, name, _ in operations if operation == "create_table"] == ["dataset_examples"]
    assert {name for operation, name, _ in operations if operation == "create_index"} == {"uq_dataset_examples_dataset_example_id", "ix_dataset_examples_dataset_version_id", "ix_dataset_examples_expected_category_id", "ix_dataset_examples_expected_department_id"}
    assert not hasattr(module._urgency, "create_called")
    operations.clear(); module.downgrade()
    assert [name for operation, name, _ in operations if operation == "drop_table"] == ["dataset_examples"]
    assert len([1 for operation, _, _ in operations if operation == "drop_index"]) == 4
