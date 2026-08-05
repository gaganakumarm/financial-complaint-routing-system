"""Deployment-candidate persistence contract tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Enum, Text, Uuid

from app.models import BenchmarkResult, DeploymentCandidate, DeploymentCandidateStatus, ModelPromotionDecision, ModelVersion, User


def indexes(table): return {index.name: index for index in table.indexes}


def test_columns_types_enum_nullability_and_defaults() -> None:
    table = DeploymentCandidate.__table__
    assert table.name == "deployment_candidates"
    assert set(table.c.keys()) == {"id", "model_promotion_decision_id", "benchmark_result_id", "model_version_id", "status", "registered_by_user_id", "registered_at", "staged_at", "activated_at", "retired_at", "retirement_reason", "notes", "created_at", "updated_at"}
    assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
    assert isinstance(table.c.status.type, Enum) and table.c.status.type.name == "deployment_candidate_status"
    assert table.c.status.type.enums == ["candidate", "staged", "active", "retired", "rejected"]
    assert [item.value for item in DeploymentCandidateStatus] == ["candidate", "staged", "active", "retired", "rejected"]
    assert str(table.c.status.server_default.arg) == "candidate"
    assert isinstance(table.c.retirement_reason.type, Text) and isinstance(table.c.notes.type, Text)
    assert all(not table.c[name].nullable for name in ("id", "model_promotion_decision_id", "benchmark_result_id", "model_version_id", "status", "registered_by_user_id", "registered_at", "created_at", "updated_at"))
    assert all(table.c[name].nullable for name in ("staged_at", "activated_at", "retired_at", "retirement_reason", "notes"))
    for name in ("registered_at", "staged_at", "activated_at", "retired_at", "created_at", "updated_at"):
        assert isinstance(table.c[name].type, DateTime) and table.c[name].type.timezone


def test_foreign_keys_are_explicit_restrict_and_required() -> None:
    table = DeploymentCandidate.__table__
    expected = {
        "model_promotion_decision_id": ("model_promotion_decisions.id", "fk_deployment_candidates_promotion_id"),
        "benchmark_result_id": ("benchmark_results.id", "fk_deployment_candidates_result_id"),
        "model_version_id": ("model_versions.id", "fk_deployment_candidates_model_version_id"),
        "registered_by_user_id": ("users.id", "fk_deployment_candidates_registered_by_user_id"),
    }
    for name, (target, constraint) in expected.items():
        foreign_key = next(iter(table.c[name].foreign_keys))
        assert (foreign_key.target_fullname, foreign_key.constraint.name, foreign_key.ondelete, table.c[name].nullable) == (target, constraint, "RESTRICT", False)


def test_check_constraints_are_exact() -> None:
    assert {constraint.name for constraint in DeploymentCandidate.__table__.constraints if isinstance(constraint, CheckConstraint)} == {
        "ck_deployment_candidates_retirement_reason_not_blank", "ck_deployment_candidates_notes_not_blank",
        "ck_deployment_candidates_candidate_consistency", "ck_deployment_candidates_staged_consistency",
        "ck_deployment_candidates_active_consistency", "ck_deployment_candidates_retired_consistency",
        "ck_deployment_candidates_rejected_consistency", "ck_deployment_candidates_staged_at_order",
        "ck_deployment_candidates_activated_at_order", "ck_deployment_candidates_retired_at_order",
    }


def test_indexes_promotion_uniqueness_and_single_active_predicate() -> None:
    expected = indexes(DeploymentCandidate.__table__)
    assert set(expected) == {
        "uq_deployment_candidates_promotion_id", "ix_deployment_candidates_result_id",
        "ix_deployment_candidates_model_version_id", "ix_deployment_candidates_status",
        "ix_deployment_candidates_registered_by_user_id", "ix_deployment_candidates_registered_at",
        "ix_deployment_candidates_staged_at", "ix_deployment_candidates_activated_at",
        "ix_deployment_candidates_retired_at", "uq_deployment_candidates_single_active",
    }
    assert expected["uq_deployment_candidates_promotion_id"].unique
    active = expected["uq_deployment_candidates_single_active"]
    assert active.unique and [column.name for column in active.columns] == ["status"]
    assert str(active.dialect_options["postgresql"]["where"]) == "status = 'active'"


def test_relationships_are_bidirectional_one_to_one_and_wire_in_memory() -> None:
    assert DeploymentCandidate.model_promotion_decision.property.back_populates == "deployment_candidate"
    assert ModelPromotionDecision.deployment_candidate.property.back_populates == "model_promotion_decision"
    assert ModelPromotionDecision.deployment_candidate.property.uselist is False
    assert DeploymentCandidate.benchmark_result.property.back_populates == "deployment_candidates"
    assert DeploymentCandidate.model_version.property.back_populates == "deployment_candidates"
    assert DeploymentCandidate.registered_by_user.property.back_populates == "registered_deployment_candidates"
    promotion, result, model, user = ModelPromotionDecision(), BenchmarkResult(), ModelVersion(), User()
    candidate = DeploymentCandidate(model_promotion_decision=promotion, benchmark_result=result, model_version=model, registered_by_user=user)
    assert promotion.deployment_candidate is candidate
    assert candidate in result.deployment_candidates and candidate in model.deployment_candidates and candidate in user.registered_deployment_candidates


def test_exports_revision_and_single_head() -> None:
    import app.models as models
    assert models.DeploymentCandidate is DeploymentCandidate and models.DeploymentCandidateStatus is DeploymentCandidateStatus
    assert {"DeploymentCandidate", "DeploymentCandidateStatus"} <= set(models.__all__)
    script = ScriptDirectory.from_config(Config("alembic.ini")); revision = script.get_revision("20260805_10")
    assert revision.down_revision == "20260805_09" and script.get_heads() == ["20260805_10"]


def test_migration_upgrade_downgrade_enum_table_and_indexes(monkeypatch) -> None:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260805_10").module; operations = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module._status, "create", lambda bind, checkfirst: operations.append(("create_enum", checkfirst)))
    monkeypatch.setattr(module._status, "drop", lambda bind, checkfirst: operations.append(("drop_enum", checkfirst)))
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name, kwargs)))
    module.upgrade()
    assert operations[0] == ("create_enum", True)
    assert [item[1] for item in operations if item[0] == "create_table"] == ["deployment_candidates"]
    indexes_created = [item for item in operations if item[0] == "create_index"]
    assert len(indexes_created) == 10
    active = next(item for item in indexes_created if item[1] == "uq_deployment_candidates_single_active")
    assert active[2]["unique"] is True and str(active[2]["postgresql_where"]) == "status = 'active'"
    operations.clear(); module.downgrade()
    assert len([item for item in operations if item[0] == "drop_index"]) == 10
    assert [item[1] for item in operations if item[0] == "drop_table"] == ["deployment_candidates"]
    assert operations[-1] == ("drop_enum", True)
