"""Benchmark comparison model and migration contract tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid

from app.models import BenchmarkComparison, BenchmarkComparisonMember, BenchmarkExperiment, DatasetVersion, User


def indexes(table):
    return {index.name: index for index in table.indexes}


def test_comparison_columns_constraints_indexes_and_foreign_keys() -> None:
    table = BenchmarkComparison.__table__
    assert table.name == "benchmark_comparisons"
    assert set(table.c) == {table.c.id, table.c.dataset_version_id, table.c.dataset_checksum, table.c.dataset_example_count, table.c.winner_result_id, table.c.ranking_metric, table.c.created_by_user_id, table.c.created_at, table.c.updated_at}
    assert isinstance(table.c.id.type, Uuid) and table.c.id.primary_key
    assert isinstance(table.c.dataset_checksum.type, String) and table.c.dataset_checksum.type.length == 128
    assert isinstance(table.c.dataset_example_count.type, Integer)
    assert isinstance(table.c.ranking_metric.type, String) and table.c.ranking_metric.type.length == 100
    assert all(not column.nullable for column in table.c)
    assert isinstance(table.c.created_at.type, DateTime) and table.c.created_at.type.timezone
    assert {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)} == {"ck_benchmark_comparisons_dataset_checksum_not_blank", "ck_benchmark_comparisons_example_count_positive", "ck_benchmark_comparisons_ranking_metric_not_blank"}
    expected_fks = {"dataset_version_id": ("dataset_versions.id", "fk_benchmark_comparisons_dataset_version_id"), "winner_result_id": ("benchmark_results.id", "fk_benchmark_comparisons_winner_result_id"), "created_by_user_id": ("users.id", "fk_benchmark_comparisons_created_by_user_id")}
    for name, (target, constraint) in expected_fks.items():
        foreign_key = next(iter(table.c[name].foreign_keys)); assert (foreign_key.target_fullname, foreign_key.constraint.name, foreign_key.ondelete) == (target, constraint, "RESTRICT")
    assert set(indexes(table)) == {"ix_benchmark_comparisons_dataset_version_id", "ix_benchmark_comparisons_winner_result_id", "ix_benchmark_comparisons_created_by_user_id", "ix_benchmark_comparisons_created_at"}


def test_member_columns_constraints_uniqueness_indexes_and_foreign_keys() -> None:
    table = BenchmarkComparisonMember.__table__
    assert table.name == "benchmark_comparison_members"
    assert set(table.c.keys()) == {"id", "benchmark_comparison_id", "benchmark_result_id", "rank", "created_at"}
    assert all(not column.nullable for column in table.c)
    assert {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)} == {"ck_benchmark_comparison_members_rank_positive"}
    expected = indexes(table)
    assert set(expected) == {"uq_benchmark_comparison_members_comparison_result", "uq_benchmark_comparison_members_comparison_rank", "ix_benchmark_comparison_members_comparison_id", "ix_benchmark_comparison_members_result_id", "ix_benchmark_comparison_members_rank"}
    assert expected["uq_benchmark_comparison_members_comparison_result"].unique
    assert expected["uq_benchmark_comparison_members_comparison_rank"].unique
    comparison_fk = next(iter(table.c.benchmark_comparison_id.foreign_keys)); experiment_fk = next(iter(table.c.benchmark_result_id.foreign_keys))
    assert (comparison_fk.constraint.name, comparison_fk.ondelete) == ("fk_benchmark_comparison_members_comparison_id", "CASCADE")
    assert (experiment_fk.constraint.name, experiment_fk.ondelete) == ("fk_benchmark_comparison_members_result_id", "RESTRICT")


def test_relationships_are_bidirectional() -> None:
    assert BenchmarkComparison.members.property.back_populates == "comparison"
    assert BenchmarkComparison.dataset_version.property.back_populates == "benchmark_comparisons"
    assert BenchmarkComparison.winner_result.property.back_populates == "winning_comparisons"
    assert BenchmarkComparison.created_by_user.property.back_populates == "created_benchmark_comparisons"
    assert BenchmarkComparisonMember.benchmark_result.property.back_populates == "comparison_members"
    assert DatasetVersion.benchmark_comparisons.property.back_populates == "dataset_version"
    assert User.created_benchmark_comparisons.property.back_populates == "created_by_user"


def test_relationship_collections_work_in_memory() -> None:
    from app.models import BenchmarkResult
    dataset, winner, creator = DatasetVersion(), BenchmarkResult(), User()
    comparison = BenchmarkComparison(dataset_version=dataset, winner_result=winner, created_by_user=creator)
    member = BenchmarkComparisonMember(comparison=comparison, benchmark_result=winner, rank=1)
    assert comparison in dataset.benchmark_comparisons
    assert comparison in winner.winning_comparisons
    assert comparison in creator.created_benchmark_comparisons
    assert member in comparison.members and member in winner.comparison_members


def test_models_are_exported_and_migration_is_single_head() -> None:
    import app.models as models
    assert models.BenchmarkComparison is BenchmarkComparison
    assert models.BenchmarkComparisonMember is BenchmarkComparisonMember
    assert {"BenchmarkComparison", "BenchmarkComparisonMember"} <= set(models.__all__)
    script = ScriptDirectory.from_config(Config("alembic.ini")); revision = script.get_revision("20260805_07")
    assert revision.down_revision == "20260805_06"
    assert script.get_heads() == ["20260805_11"]


def test_migration_upgrade_and_downgrade_operations(monkeypatch) -> None:
    module = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20260805_07").module
    operations = []
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name, kwargs)))
    module.upgrade()
    assert [name for operation, name, _ in operations if operation == "create_table"] == ["benchmark_comparisons", "benchmark_comparison_members"]
    assert len([1 for operation, _, _ in operations if operation == "create_index"]) == 9
    operations.clear(); module.downgrade()
    assert [name for operation, name, _ in operations if operation == "drop_table"] == ["benchmark_comparison_members", "benchmark_comparisons"]
    assert len([1 for operation, _, _ in operations if operation == "drop_index"]) == 9
