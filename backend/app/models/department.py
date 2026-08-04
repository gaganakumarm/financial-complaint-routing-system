"""Department model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A department available as a final complaint destination."""

    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="ck_departments_code_not_blank"),
        CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_departments_display_name_not_blank",
        ),
        Index("uq_departments_code", "code", unique=True),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    complaints: Mapped[list[Complaint]] = relationship(
        back_populates="final_department"
    )
