"""Tests for dataset versioning and benchmark persistence."""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.models import (
    BenchmarkExperiment,
    BenchmarkExperimentStatus,
    BenchmarkResult,
    DatasetSplit,
    DatasetVersion,
    ModelType,
    ModelVersion,
)


EXPECTED_TABLES = {
    "roles", "users", "complaint_categories", "departments", "complaints",
    "complaint_status_history", "model_versions", "predictions", "reviews",
    "dataset_versions", "dataset_examples", "benchmark_experiments", "benchmark_results",
}


def test_benchmark_metadata_and_enums() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert [item.value for item in DatasetSplit] == ["train", "validation", "test", "full"]
    assert [item.value for item in BenchmarkExperimentStatus] == [
        "pending", "running", "completed", "failed", "cancelled",
    ]
    assert DatasetVersion.__table__.c.split.type.name == "dataset_split"
    assert DatasetVersion.__table__.c.split.type.enums == [item.value for item in DatasetSplit]
    assert BenchmarkExperiment.__table__.c.status.type.name == "benchmark_experiment_status"


def test_dataset_version_schema() -> None:
    table = DatasetVersion.__table__
    assert set(table.c.keys()) == {
        "id", "name", "version", "source_name", "source_reference",
        "taxonomy_version", "split", "record_count", "content_hash",
        "preparation_details", "created_at",
    }
    assert "updated_at" not in table.c
    assert table.c.name.type.length == 100 and table.c.name.nullable is False
    assert table.c.version.type.length == 50
    assert table.c.source_name.type.length == 200
    assert table.c.source_reference.nullable is True
    assert table.c.taxonomy_version.type.length == 50
    assert table.c.content_hash.type.length == 128
    assert isinstance(table.c.preparation_details.type, JSONB)
    assert table.c.preparation_details.default is None
    _assert_timestamp(table.c.created_at)
    assert _check_names(table) == {
        "ck_dataset_versions_name_not_blank", "ck_dataset_versions_version_not_blank",
        "ck_dataset_versions_source_name_not_blank",
        "ck_dataset_versions_taxonomy_version_not_blank",
        "ck_dataset_versions_content_hash_not_blank",
        "ck_dataset_versions_record_count_positive",
    }
    expected = {
        "uq_dataset_versions_name_version_split": ["name", "version", "split"],
        "uq_dataset_versions_content_hash": ["content_hash"],
        "ix_dataset_versions_split": ["split"],
        "ix_dataset_versions_taxonomy_version": ["taxonomy_version"],
    }
    _assert_indexes(table, expected)
    assert _index(table, "uq_dataset_versions_name_version_split").unique is True
    assert _index(table, "uq_dataset_versions_content_hash").unique is True
    assert DatasetVersion.benchmark_experiments.property.back_populates == "dataset_version"
    assert "delete" not in DatasetVersion.benchmark_experiments.property.cascade


def test_benchmark_experiment_schema() -> None:
    table = BenchmarkExperiment.__table__
    assert set(table.c.keys()) == {
        "id", "name", "dataset_version_id", "status", "configuration",
        "started_at", "completed_at", "failure_message", "created_at",
    }
    assert "updated_at" not in table.c
    foreign_key = next(iter(table.c.dataset_version_id.foreign_keys))
    assert foreign_key.target_fullname == "dataset_versions.id"
    assert foreign_key.constraint.name == "fk_benchmark_experiments_dataset_version_id"
    assert foreign_key.ondelete == "RESTRICT"
    assert table.c.status.default.arg is BenchmarkExperimentStatus.PENDING
    assert str(table.c.status.server_default.arg) == "pending"
    assert isinstance(table.c.configuration.type, JSONB)
    assert table.c.configuration.nullable is False and table.c.configuration.default is None
    for name in ("started_at", "completed_at", "created_at"):
        _assert_timestamp(table.c[name])
    assert _check_names(table) == {
        "ck_benchmark_experiments_name_not_blank",
        "ck_benchmark_experiments_timestamps_order",
        "ck_benchmark_experiments_pending_consistency",
        "ck_benchmark_experiments_running_requires_started_at",
        "ck_benchmark_experiments_completed_requires_timestamps",
        "ck_benchmark_experiments_failed_requires_completion",
        "ck_benchmark_experiments_failure_message_consistency",
    }
    _assert_indexes(table, {
        "ix_benchmark_experiments_dataset_version_id": ["dataset_version_id"],
        "ix_benchmark_experiments_status": ["status"],
        "ix_benchmark_experiments_status_created_at": ["status", "created_at"],
    })
    assert BenchmarkExperiment.dataset_version.property.back_populates == "benchmark_experiments"
    assert BenchmarkExperiment.results.property.back_populates == "experiment"
    assert "delete" not in BenchmarkExperiment.results.property.cascade


def test_benchmark_result_schema() -> None:
    table = BenchmarkResult.__table__
    assert set(table.c.keys()) == {
        "id", "benchmark_experiment_id", "model_version_id", "sample_count",
        "accuracy", "macro_precision", "macro_recall", "macro_f1",
        "cost_weighted_error", "structured_output_validity_rate",
        "average_inference_latency_ms", "throughput_per_second", "estimated_cost",
        "per_class_metrics", "additional_metrics", "created_at",
    }
    assert "updated_at" not in table.c
    for column_name, target, constraint_name in (
        ("benchmark_experiment_id", "benchmark_experiments.id", "fk_benchmark_results_experiment_id"),
        ("model_version_id", "model_versions.id", "fk_benchmark_results_model_version_id"),
    ):
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.constraint.name == constraint_name
        assert foreign_key.ondelete == "RESTRICT"
    numerics = {
        "accuracy": (6, 5), "macro_precision": (6, 5), "macro_recall": (6, 5),
        "macro_f1": (6, 5), "structured_output_validity_rate": (6, 5),
        "cost_weighted_error": (14, 6), "average_inference_latency_ms": (14, 4),
        "throughput_per_second": (14, 4), "estimated_cost": (16, 6),
    }
    for name, (precision, scale) in numerics.items():
        assert isinstance(table.c[name].type, Numeric)
        assert (table.c[name].type.precision, table.c[name].type.scale) == (precision, scale)
    assert isinstance(table.c.per_class_metrics.type, JSONB)
    assert isinstance(table.c.additional_metrics.type, JSONB)
    assert table.c.per_class_metrics.default is None
    assert table.c.additional_metrics.default is None
    assert _check_names(table) == {
        "ck_benchmark_results_sample_count_positive",
        "ck_benchmark_results_accuracy_range",
        "ck_benchmark_results_macro_precision_range",
        "ck_benchmark_results_macro_recall_range",
        "ck_benchmark_results_macro_f1_range",
        "ck_benchmark_results_validity_rate_range",
        "ck_benchmark_results_cost_weighted_error_non_negative",
        "ck_benchmark_results_latency_non_negative",
        "ck_benchmark_results_throughput_non_negative",
        "ck_benchmark_results_estimated_cost_non_negative",
    }
    expected = {
        "uq_benchmark_results_experiment_model": ["benchmark_experiment_id", "model_version_id"],
        "ix_benchmark_results_experiment_id": ["benchmark_experiment_id"],
        "ix_benchmark_results_model_version_id": ["model_version_id"],
        "ix_benchmark_results_model_created_at": ["model_version_id", "created_at"],
    }
    _assert_indexes(table, expected)
    assert _index(table, "uq_benchmark_results_experiment_model").unique is True
    assert BenchmarkResult.experiment.property.back_populates == "results"
    assert BenchmarkResult.model_version.property.back_populates == "benchmark_results"
    assert "delete" not in ModelVersion.benchmark_results.property.cascade


def test_benchmark_relationships_work_in_memory() -> None:
    dataset = DatasetVersion(
        name="complaints", version="1.0", source_name="Synthetic",
        taxonomy_version="1", split=DatasetSplit.TEST, record_count=10,
        content_hash="abc123",
    )
    experiment = BenchmarkExperiment(name="baseline", dataset_version=dataset, configuration={})
    model = ModelVersion(name="router", version="1", model_type=ModelType.TFIDF_CLASSIFIER)
    result = BenchmarkResult(experiment=experiment, model_version=model, sample_count=10)
    assert experiment in dataset.benchmark_experiments
    assert result in experiment.results
    assert result in model.benchmark_results


def test_benchmark_migration_operations(monkeypatch) -> None:
    revisions = list(ScriptDirectory.from_config(Config("alembic.ini")).walk_revisions())
    assert [(item.revision, item.down_revision) for item in revisions] == [
        ("20260805_06", "20260804_05"),
        ("20260804_05", "20260804_04"), ("20260804_04", "20260804_03"),
        ("20260804_03", "20260804_02"), ("20260804_02", "20260803_01"),
        ("20260803_01", None),
    ]
    module = revisions[1].module
    operations: list[tuple[str, str]] = []
    enum_operations: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    for enum_object in (module._dataset_split, module._experiment_status):
        monkeypatch.setattr(enum_object, "create", lambda bind, checkfirst, name=enum_object.name: enum_operations.append(("create", name)))
        monkeypatch.setattr(enum_object, "drop", lambda bind, checkfirst, name=enum_object.name: enum_operations.append(("drop", name)))
    for method in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(module.op, method, lambda name, *args, _method=method, **kwargs: operations.append((_method, name)))
    module.upgrade()
    assert enum_operations == [("create", "dataset_split"), ("create", "benchmark_experiment_status")]
    assert [value for operation, value in operations if operation == "create_table"] == [
        "dataset_versions", "benchmark_experiments", "benchmark_results",
    ]
    assert len([1 for operation, _ in operations if operation == "create_index"]) == 11
    operations.clear()
    module.downgrade()
    assert [value for operation, value in operations if operation == "drop_table"] == [
        "benchmark_results", "benchmark_experiments", "dataset_versions",
    ]
    assert enum_operations[-2:] == [
        ("drop", "benchmark_experiment_status"), ("drop", "dataset_split"),
    ]


def _assert_timestamp(column) -> None:
    assert isinstance(column.type, DateTime) and column.type.timezone is True


def _check_names(table) -> set[str]:
    return {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)}


def _index(table, name: str):
    return next(index for index in table.indexes if index.name == name)


def _assert_indexes(table, expected: dict[str, list[str]]) -> None:
    assert {index.name for index in table.indexes} == set(expected)
    for name, columns in expected.items():
        assert [column.name for column in _index(table, name).columns] == columns
