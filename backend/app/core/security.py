"""Password hashing, JWT issuing/verification and RBAC helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings
from app.core.constants import ROLE_PERMISSIONS, UserRole

TokenType = Literal["access", "refresh", "reset"]

# bcrypt truncates at 72 bytes; pre-hash so long passphrases keep full entropy.
_BCRYPT_MAX_BYTES = 72


def _prepare_password(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return hashlib.sha256(raw).hexdigest().encode("utf-8")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prepare_password(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@dataclass(slots=True)
class TokenPayload:
    subject: str
    role: UserRole
    token_type: TokenType
    jti: str
    issued_at: datetime
    expires_at: datetime
    session_id: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def user_id(self) -> int:
        return int(self.subject)


def create_token(
    *,
    subject: str | int,
    role: UserRole | str,
    token_type: TokenType = "access",
    expires_delta: timedelta | None = None,
    session_id: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    if expires_delta is None:
        minutes = {
            "access": settings.access_token_expire_minutes,
            "refresh": settings.refresh_token_expire_minutes,
            "reset": settings.password_reset_token_expire_minutes,
        }[token_type]
        expires_delta = timedelta(minutes=minutes)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role.value if isinstance(role, UserRole) else str(role),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.app_name,
    }
    if session_id:
        payload["sid"] = session_id
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or has the wrong type."""


def decode_token(token: str, *, expected_type: TokenType | None = "access") -> TokenPayload:
    try:
        raw = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Could not validate credentials") from exc

    token_type = raw.get("type")
    if expected_type is not None and token_type != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    try:
        role = UserRole(raw.get("role"))
    except ValueError as exc:
        raise TokenError("Token carries an unknown role") from exc

    return TokenPayload(
        subject=str(raw["sub"]),
        role=role,
        token_type=token_type,  # type: ignore[arg-type]
        jti=raw.get("jti", ""),
        issued_at=datetime.fromtimestamp(raw.get("iat", 0), tz=UTC),
        expires_at=datetime.fromtimestamp(raw["exp"], tz=UTC),
        session_id=raw.get("sid"),
        raw=raw,
    )


def permissions_for(role: UserRole) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def role_has_permission(role: UserRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def generate_password_reset_token(user_id: int, role: UserRole, password_hash: str) -> str:
    """Reset tokens embed a fingerprint of the current hash so they are single-use."""
    fingerprint = hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:32]
    return create_token(
        subject=user_id,
        role=role,
        token_type="reset",
        extra_claims={"fpr": fingerprint},
    )


def verify_password_reset_token(token: str, password_hash: str) -> TokenPayload:
    payload = decode_token(token, expected_type="reset")
    expected = hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:32]
    provided = (payload.raw or {}).get("fpr", "")
    if not hmac.compare_digest(expected, str(provided)):
        raise TokenError("This reset link has already been used")
    return payload


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
