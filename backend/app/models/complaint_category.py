"""Complaint category model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint


class ComplaintCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A controlled category available for final complaint classification."""

    __tablename__ = "complaint_categories"
    __table_args__ = (
        CheckConstraint(
            "btrim(code) <> ''",
            name="ck_complaint_categories_code_not_blank",
        ),
        CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_complaint_categories_display_name_not_blank",
        ),
        Index("uq_complaint_categories_code", "code", unique=True),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_high_risk: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    complaints: Mapped[list[Complaint]] = relationship(
        back_populates="final_category"
    )
