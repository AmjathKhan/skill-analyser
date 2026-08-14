"""Password hashing, JWT and RBAC unit tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.constants import ROLE_PERMISSIONS, UserRole
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    generate_password_reset_token,
    hash_password,
    new_session_id,
    permissions_for,
    role_has_permission,
    verify_password,
    verify_password_reset_token,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("Sup3r$ecret")
    assert hashed != "Sup3r$ecret"
    assert hashed.startswith("$2")
    assert verify_password("Sup3r$ecret", hashed)
    assert not verify_password("wrong", hashed)


def test_password_hash_is_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_long_password_is_accepted() -> None:
    """bcrypt truncates at 72 bytes; the helper pre-hashes instead of raising."""
    password = "x" * 200
    assert verify_password(password, hash_password(password))


def test_access_token_roundtrip() -> None:
    session_id = new_session_id()
    token = create_token(subject=42, role=UserRole.RECRUITER, token_type="access", session_id=session_id)
    payload = decode_token(token)
    assert payload.user_id == 42
    assert payload.token_type == "access"
    assert payload.session_id == session_id
    assert payload.role is UserRole.RECRUITER


def test_expired_token_is_rejected() -> None:
    token = create_token(subject=1, role=UserRole.HR_ADMIN, expires_delta=timedelta(seconds=-10))
    with pytest.raises(TokenError):
        decode_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_token(subject=1, role=UserRole.HR_ADMIN)
    with pytest.raises(TokenError):
        decode_token(token[:-3] + "abc")


def test_refresh_token_cannot_be_used_as_access_token() -> None:
    token = create_token(subject=1, role=UserRole.HR_ADMIN, token_type="refresh")
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access")
    assert decode_token(token, expected_type="refresh").token_type == "refresh"


def test_password_reset_token_is_single_use() -> None:
    original_hash = hash_password("OldPassword#1")
    token = generate_password_reset_token(7, UserRole.RECRUITER, original_hash)

    payload = verify_password_reset_token(token, original_hash)
    assert payload.user_id == 7

    rotated_hash = hash_password("NewPassword#1")
    with pytest.raises(TokenError):
        verify_password_reset_token(token, rotated_hash)


def test_reset_token_rejects_access_token() -> None:
    password_hash = hash_password("Password#1")
    token = create_token(subject=7, role=UserRole.RECRUITER, token_type="access")
    with pytest.raises(TokenError):
        verify_password_reset_token(token, password_hash)


def test_rbac_matrix() -> None:
    assert role_has_permission(UserRole.HR_ADMIN, "user:manage")
    assert not role_has_permission(UserRole.RECRUITER, "user:manage")
    assert role_has_permission(UserRole.RECRUITER, "resume:upload")
    assert role_has_permission(UserRole.HIRING_MANAGER, "candidate:read")


def test_permissions_for_matches_role_matrix() -> None:
    for role in UserRole:
        assert permissions_for(role) == set(ROLE_PERMISSIONS[role])
    assert permissions_for(UserRole.HR_ADMIN) >= permissions_for(UserRole.HIRING_MANAGER)
