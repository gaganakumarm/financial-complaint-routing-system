"""Role model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A machine-readable authorization role assigned to users."""

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_roles_name_not_blank"),
        CheckConstraint(
            "btrim(display_name) <> ''",
            name="ck_roles_display_name_not_blank",
        ),
        Index("uq_roles_name", "name", unique=True),
    )

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    users: Mapped[list[User]] = relationship(back_populates="role")
