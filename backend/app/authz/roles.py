"""Canonical application-level role names."""

from enum import StrEnum


class ApplicationRole(StrEnum):
    CUSTOMER = "customer"
    REVIEWER = "reviewer"
    ADMINISTRATOR = "administrator"


def normalize_role_name(role_name: str) -> str:
    """Normalize and validate a canonical application role name."""
    if not isinstance(role_name, str):
        raise ValueError("role name must be a string")
    normalized = role_name.strip().lower()
    if not normalized:
        raise ValueError("role name cannot be blank")
    try:
        return ApplicationRole(normalized).value
    except ValueError:
        raise ValueError("role name is not supported") from None
