"""Argon2id password hashing and verification."""

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher


_password_hash = PasswordHash((Argon2Hasher(),))


def _normalize_password(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized


def hash_password(password: str) -> str:
    """Hash a normalized password using Argon2id."""
    return _password_hash.hash(_normalize_password(password, "password"))


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password, returning false for malformed or unsupported hashes."""
    normalized_password = _normalize_password(password, "password")
    normalized_hash = _normalize_password(password_hash, "password_hash")
    try:
        return _password_hash.verify(normalized_password, normalized_hash)
    except Exception:
        return False
