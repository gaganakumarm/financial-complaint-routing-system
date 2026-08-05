"""Immutable dataset-version persistence model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.benchmark_experiment import BenchmarkExperiment
    from app.models.dataset_example import DatasetExample


class DatasetSplit(StrEnum):
    """Dataset splits persisted as lowercase values."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    FULL = "full"


def dataset_split_enum() -> Enum:
    """Build the native dataset-split enum mapping."""
    return Enum(
        DatasetSplit,
        name="dataset_split",
        values_callable=lambda members: [member.value for member in members],
    )


class DatasetVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable metadata identifying reproducible dataset content."""

    __tablename__ = "dataset_versions"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    split: Mapped[DatasetSplit] = mapped_column(dataset_split_enum(), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    preparation_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_dataset_versions_name_not_blank"),
        CheckConstraint(
            "btrim(version) <> ''", name="ck_dataset_versions_version_not_blank"
        ),
        CheckConstraint(
            "btrim(source_name) <> ''",
            name="ck_dataset_versions_source_name_not_blank",
        ),
        CheckConstraint(
            "btrim(taxonomy_version) <> ''",
            name="ck_dataset_versions_taxonomy_version_not_blank",
        ),
        CheckConstraint(
            "btrim(content_hash) <> ''",
            name="ck_dataset_versions_content_hash_not_blank",
        ),
        CheckConstraint(
            "record_count > 0",
            name="ck_dataset_versions_record_count_positive",
        ),
        Index(
            "uq_dataset_versions_name_version_split",
            "name",
            "version",
            "split",
            unique=True,
        ),
        Index("uq_dataset_versions_content_hash", "content_hash", unique=True),
        Index("ix_dataset_versions_split", "split"),
        Index("ix_dataset_versions_taxonomy_version", "taxonomy_version"),
    )

    benchmark_experiments: Mapped[list[BenchmarkExperiment]] = relationship(
        back_populates="dataset_version"
    )
    examples: Mapped[list[DatasetExample]] = relationship(back_populates="dataset_version")
