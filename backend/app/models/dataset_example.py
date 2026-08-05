"""Persisted labeled examples belonging to a dataset version."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, utc_now
from app.models.complaint import ComplaintUrgency, complaint_urgency_enum

if TYPE_CHECKING:
    from app.models.complaint_category import ComplaintCategory
    from app.models.dataset_version import DatasetVersion
    from app.models.department import Department


class DatasetExample(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dataset_examples"

    dataset_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dataset_versions.id", name="fk_dataset_examples_dataset_version_id", ondelete="RESTRICT"), nullable=False)
    example_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_category_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("complaint_categories.id", name="fk_dataset_examples_expected_category_id", ondelete="RESTRICT"), nullable=False)
    expected_department_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", name="fk_dataset_examples_expected_department_id", ondelete="RESTRICT"), nullable=False)
    expected_urgency: Mapped[ComplaintUrgency] = mapped_column(complaint_urgency_enum(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("btrim(example_id) <> ''", name="ck_dataset_examples_example_id_not_blank"),
        CheckConstraint("btrim(title) <> ''", name="ck_dataset_examples_title_not_blank"),
        CheckConstraint("btrim(description) <> ''", name="ck_dataset_examples_description_not_blank"),
        Index("uq_dataset_examples_dataset_example_id", "dataset_version_id", "example_id", unique=True),
        Index("ix_dataset_examples_dataset_version_id", "dataset_version_id"),
        Index("ix_dataset_examples_expected_category_id", "expected_category_id"),
        Index("ix_dataset_examples_expected_department_id", "expected_department_id"),
    )

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="examples")
    expected_category: Mapped[ComplaintCategory] = relationship(back_populates="dataset_examples")
    expected_department: Mapped[Department] = relationship(back_populates="dataset_examples")
