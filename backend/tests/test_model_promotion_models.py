"""Model-promotion persistence and migration contract tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Text, Uuid

from app.models import (
    BenchmarkComparison,
    BenchmarkResult,
    ModelPromotionDecision,
    ModelPromotionStatus,
    ModelVersion,
    User,
)


def indexes(table):
    return {index.name: index for index in table.indexes}


def test_table_columns_types_nullability_defaults_and_enum() -> None:
    table = ModelPromotionDecision.__table__
    assert table.name == "model_promotion_decisions"
    assert set(table.c.keys()) == {
        "id", "benchmark_comparison_id", "selected_benchmark_result_id",
        "selected_model_version_id", "status", "rationale", "override_winner",
        "requested_by_user_id", "reviewed_by_user_id", "requested_at",
        "reviewed_at", "review_note", "created_at", "updated_at",
    }
    assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
    assert isinstance(table.c.status.type, Enum)
    assert table.c.status.type.name == "model_promotion_status"
    assert table.c.status.type.enums == ["pending", "approved", "rejected", "cancelled"]
    assert list(ModelPromotionStatus) == [
        ModelPromotionStatus.PENDING, ModelPromotionStatus.APPROVED,
        ModelPromotionStatus.REJECTED, ModelPromotionStatus.CANCELLED,
    ]
    assert isinstance(table.c.rationale.type, Text) and isinstance(table.c.review_note.type, Text)
    assert isinstance(table.c.override_winner.type, Boolean)
    assert str(table.c.override_winner.server_default.arg).lower() == "false"
    assert not table.c.requested_at.nullable and not table.c.override_winner.nullable
    assert table.c.reviewed_at.nullable and table.c.reviewed_by_user_id.nullable and table.c.review_note.nullable
    for name in ("requested_at", "reviewed_at", "created_at", "updated_at"):
        assert isinstance(table.c[name].type, DateTime) and table.c[name].type.timezone


def test_foreign_keys_are_named_restrict_and_nullable_as_required() -> None:
    table = ModelPromotionDecision.__table__
    expected = {
        "benchmark_comparison_id": ("benchmark_comparisons.id", "fk_model_promotion_decisions_comparison_id"),
        "selected_benchmark_result_id": ("benchmark_results.id", "fk_model_promotion_decisions_result_id"),
        "selected_model_version_id": ("model_versions.id", "fk_model_promotion_decisions_model_version_id"),
        "requested_by_user_id": ("users.id", "fk_model_promotion_decisions_requested_by_user_id"),
        "reviewed_by_user_id": ("users.id", "fk_model_promotion_decisions_reviewed_by_user_id"),
    }
    for column_name, (target, constraint_name) in expected.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert (foreign_key.target_fullname, foreign_key.constraint.name, foreign_key.ondelete) == (target, constraint_name, "RESTRICT")
        assert table.c[column_name].nullable is (column_name == "reviewed_by_user_id")


def test_check_constraints_and_indexes_are_exact() -> None:
    table = ModelPromotionDecision.__table__
    assert {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)} == {
        "ck_model_promotion_decisions_rationale_not_blank",
        "ck_model_promotion_decisions_review_note_not_blank",
        "ck_model_promotion_decisions_pending_review_fields_absent",
        "ck_model_promotion_decisions_terminal_review_fields_present",
        "ck_model_promotion_decisions_review_timestamps_order",
    }
    expected = indexes(table)
    assert set(expected) == {
        "ix_model_promotion_decisions_comparison_id",
        "ix_model_promotion_decisions_result_id",
        "ix_model_promotion_decisions_model_version_id",
        "ix_model_promotion_decisions_status",
        "ix_model_promotion_decisions_requested_by_user_id",
        "ix_model_promotion_decisions_reviewed_by_user_id",
        "ix_model_promotion_decisions_requested_at",
        "ix_model_promotion_decisions_reviewed_at",
        "uq_model_promotion_decisions_pending_comparison",
    }
    partial = expected["uq_model_promotion_decisions_pending_comparison"]
    assert partial.unique
    assert [column.name for column in partial.columns] == ["benchmark_comparison_id"]
    assert str(partial.dialect_options["postgresql"]["where"]) == "status = 'pending'"


def test_relationships_are_bidirectional_and_wire_in_memory() -> None:
    assert ModelPromotionDecision.benchmark_comparison.property.back_populates == "model_promotion_decisions"
    assert ModelPromotionDecision.selected_benchmark_result.property.back_populates == "model_promotion_decisions"
    assert ModelPromotionDecision.selected_model_version.property.back_populates == "model_promotion_decisions"
    assert ModelPromotionDecision.requested_by_user.property.back_populates == "requested_model_promotions"
    assert ModelPromotionDecision.reviewed_by_user.property.back_populates == "reviewed_model_promotions"
    comparison, result, model, requester, reviewer = BenchmarkComparison(), BenchmarkResult(), ModelVersion(), User(), User()
    decision = ModelPromotionDecision(
        benchmark_comparison=comparison, selected_benchmark_result=result,
        selected_model_version=model, requested_by_user=requester,
        reviewed_by_user=reviewer,
    )
    assert decision in comparison.model_promotion_decisions
    assert decision in result.model_promotion_decisions
    assert decision in model.model_promotion_decisions
    assert decision in requester.requested_model_promotions
    assert decision in reviewer.reviewed_model_promotions


def test_exports_and_migration_chain() -> None:
    import app.models as models
    assert models.ModelPromotionDecision is ModelPromotionDecision
    assert models.ModelPromotionStatus is ModelPromotionStatus
    assert {"ModelPromotionDecision", "ModelPromotionStatus"} <= set(models.__all__)
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("20260805_09")
    assert revision.down_revision == "20260805_08"
    assert script.get_heads() == ["20260805_10"]


def test_migration_upgrade_and_downgrade(monkeypatch) -> None:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260805_09").module
    operations = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module._status, "create", lambda bind, checkfirst: operations.append(("create_enum", checkfirst)))
    monkeypatch.setattr(module._status, "drop", lambda bind, checkfirst: operations.append(("drop_enum", checkfirst)))
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name, kwargs)))
    module.upgrade()
    assert operations[0] == ("create_enum", True)
    assert [entry[1] for entry in operations if entry[0] == "create_table"] == ["model_promotion_decisions"]
    created_indexes = [entry for entry in operations if entry[0] == "create_index"]
    assert len(created_indexes) == 9
    partial = next(entry for entry in created_indexes if entry[1] == "uq_model_promotion_decisions_pending_comparison")
    assert partial[2]["unique"] is True
    assert str(partial[2]["postgresql_where"]) == "status = 'pending'"
    operations.clear(); module.downgrade()
    assert len([entry for entry in operations if entry[0] == "drop_index"]) == 9
    assert [entry[1] for entry in operations if entry[0] == "drop_table"] == ["model_promotion_decisions"]
    assert operations[-1] == ("drop_enum", True)
