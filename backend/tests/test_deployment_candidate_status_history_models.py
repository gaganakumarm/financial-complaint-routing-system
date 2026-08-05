"""Deployment-candidate status-history persistence contract tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Enum, Text, Uuid

from app.models import (
    DeploymentCandidate,
    DeploymentCandidateStatus,
    DeploymentCandidateStatusHistory,
    User,
)


def test_columns_types_nullability_and_append_only_timestamps() -> None:
    table = DeploymentCandidateStatusHistory.__table__
    assert table.name == "deployment_candidate_status_history"
    assert set(table.c.keys()) == {
        "id", "deployment_candidate_id", "previous_status", "new_status",
        "changed_by_user_id", "note", "changed_at",
    }
    assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
    assert isinstance(table.c.note.type, Text)
    assert isinstance(table.c.changed_at.type, DateTime) and table.c.changed_at.type.timezone
    assert table.c.previous_status.nullable and table.c.note.nullable
    assert all(not table.c[name].nullable for name in ("id", "deployment_candidate_id", "new_status", "changed_by_user_id", "changed_at"))
    assert "updated_at" not in table.c
    for name in ("previous_status", "new_status"):
        assert isinstance(table.c[name].type, Enum)
        assert table.c[name].type.name == "deployment_candidate_status"
        assert table.c[name].type.enums == [item.value for item in DeploymentCandidateStatus]


def test_foreign_keys_are_explicit_restrict_and_required() -> None:
    table = DeploymentCandidateStatusHistory.__table__
    expected = {
        "deployment_candidate_id": ("deployment_candidates.id", "fk_deployment_candidate_status_history_candidate_id", "CASCADE"),
        "changed_by_user_id": ("users.id", "fk_deployment_candidate_status_history_changed_by_user_id", "RESTRICT"),
    }
    for column_name, (target, constraint_name, ondelete) in expected.items():
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert (foreign_key.target_fullname, foreign_key.constraint.name, foreign_key.ondelete) == (target, constraint_name, ondelete)


def test_constraints_and_indexes_are_exact() -> None:
    table = DeploymentCandidateStatusHistory.__table__
    assert {item.name for item in table.constraints if isinstance(item, CheckConstraint)} == {
        "ck_deployment_candidate_status_history_note_not_blank",
        "ck_deployment_candidate_status_history_status_changed",
        "ck_deployment_candidate_status_history_initial_registration",
        "ck_deployment_candidate_status_history_previous_status_required",
    }
    assert {item.name: [column.name for column in item.columns] for item in table.indexes} == {
        "ix_deployment_candidate_status_history_candidate_chronology": ["deployment_candidate_id", "changed_at", "id"],
        "ix_deployment_candidate_status_history_changed_by_user_id": ["changed_by_user_id"],
        "ix_deployment_candidate_status_history_new_status": ["new_status"],
        "ix_deployment_candidate_status_history_changed_at": ["changed_at"],
    }


def test_relationships_are_bidirectional_and_wire_in_memory() -> None:
    assert DeploymentCandidateStatusHistory.deployment_candidate.property.back_populates == "status_history"
    assert DeploymentCandidate.status_history.property.back_populates == "deployment_candidate"
    assert DeploymentCandidateStatusHistory.changed_by_user.property.back_populates == "deployment_candidate_status_changes"
    assert User.deployment_candidate_status_changes.property.back_populates == "changed_by_user"
    ordering = DeploymentCandidate.status_history.property.order_by
    assert [item.element.name for item in ordering] == ["changed_at", "id"]
    assert all(item.modifier.__name__ == "asc_op" for item in ordering)
    candidate, actor = DeploymentCandidate(), User()
    event = DeploymentCandidateStatusHistory(
        deployment_candidate=candidate,
        previous_status=None,
        new_status=DeploymentCandidateStatus.CANDIDATE,
        changed_by_user=actor,
    )
    assert event in candidate.status_history
    assert event in actor.deployment_candidate_status_changes


def test_export_revision_and_single_head() -> None:
    import app.models as models
    assert models.DeploymentCandidateStatusHistory is DeploymentCandidateStatusHistory
    assert "DeploymentCandidateStatusHistory" in models.__all__
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("20260805_11")
    assert revision.down_revision == "20260805_10"
    assert script.get_heads() == ["20260805_11"]


def test_registration_constraints_encode_initial_status_contract() -> None:
    checks = {
        item.name: str(item.sqltext)
        for item in DeploymentCandidateStatusHistory.__table__.constraints
        if isinstance(item, CheckConstraint)
    }
    assert checks["ck_deployment_candidate_status_history_initial_registration"] == "previous_status IS NOT NULL OR new_status = 'candidate'"
    assert checks["ck_deployment_candidate_status_history_previous_status_required"] == "new_status = 'candidate' OR previous_status IS NOT NULL"
    assert checks["ck_deployment_candidate_status_history_status_changed"] == "previous_status IS NULL OR previous_status <> new_status"
    allowed = {"previous_status": None, "new_status": DeploymentCandidateStatus.CANDIDATE}
    rejected = [
        {"previous_status": None, "new_status": status}
        for status in DeploymentCandidateStatus
        if status is not DeploymentCandidateStatus.CANDIDATE
    ]
    assert allowed["previous_status"] is None and allowed["new_status"] is DeploymentCandidateStatus.CANDIDATE
    assert all(row["previous_status"] is None and row["new_status"] is not DeploymentCandidateStatus.CANDIDATE for row in rejected)


def test_migration_upgrade_and_downgrade(monkeypatch) -> None:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260805_11").module
    operations = []
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name, args, kwargs)))
    module.upgrade()
    create_table = next(item for item in operations if item[0] == "create_table")
    constraints = create_table[2]
    assert {item.name for item in constraints if isinstance(item, CheckConstraint)} == {
        "ck_deployment_candidate_status_history_note_not_blank",
        "ck_deployment_candidate_status_history_status_changed",
        "ck_deployment_candidate_status_history_initial_registration",
        "ck_deployment_candidate_status_history_previous_status_required",
    }
    foreign_keys = {item.name: item for item in constraints if item.__class__.__name__ == "ForeignKeyConstraint"}
    assert foreign_keys["fk_deployment_candidate_status_history_candidate_id"].ondelete == "CASCADE"
    assert foreign_keys["fk_deployment_candidate_status_history_changed_by_user_id"].ondelete == "RESTRICT"
    indexes = [item for item in operations if item[0] == "create_index"]
    assert len(indexes) == 4
    chronology = next(item for item in indexes if item[1] == "ix_deployment_candidate_status_history_candidate_chronology")
    assert chronology[2][1] == ["deployment_candidate_id", "changed_at", "id"]
    operations.clear()
    monkeypatch.setattr(module._status, "drop", lambda *args, **kwargs: operations.append(("drop_enum", "deployment_candidate_status", args, kwargs)))
    module.downgrade()
    assert len([item for item in operations if item[0] == "drop_index"]) == 4
    assert [item[1] for item in operations if item[0] == "drop_table"] == ["deployment_candidate_status_history"]
    assert not any(item[0] == "drop_enum" for item in operations)
