"""Authentication, session lifecycle and user administration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuditAction, UserRole
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    generate_password_reset_token,
    hash_password,
    new_session_id,
    permissions_for,
    verify_password,
    verify_password_reset_token,
)
from app.models.user import User, UserSession
from app.services.audit import record_audit

logger = get_logger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    session_id: str = ""


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.email) == (email or "").strip().lower()))


def authenticate(
    session: Session,
    *,
    email: str,
    password: str,
    remember_me: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, AuthTokens]:
    user = get_user_by_email(session, email)
    now = datetime.now(UTC)

    if user is None:
        record_audit(
            session,
            action=AuditAction.LOGIN_FAILED,
            actor_email=email,
            description="Login attempt for unknown email",
            ip_address=ip_address,
            user_agent=user_agent,
            status="failure",
        )
        # Same message for unknown users and bad passwords (no account enumeration).
        raise AuthenticationError("Invalid email or password")

    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60))
        raise AuthenticationError(f"Account locked due to failed attempts. Try again in {minutes} minute(s).")

    if not user.is_active:
        raise AuthenticationError("This account has been deactivated. Contact your HR administrator.")

    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        record_audit(
            session,
            action=AuditAction.LOGIN_FAILED,
            user_id=user.id,
            actor_email=user.email,
            description="Incorrect password",
            ip_address=ip_address,
            user_agent=user_agent,
            status="failure",
        )
        raise AuthenticationError("Invalid email or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    tokens = issue_tokens(
        session,
        user,
        remember_me=remember_me,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    record_audit(
        session,
        action=AuditAction.LOGIN,
        user_id=user.id,
        actor_email=user.email,
        description=f"Signed in as {user.role}",
        ip_address=ip_address,
        user_agent=user_agent,
        meta={"remember_me": remember_me},
    )
    return user, tokens


def issue_tokens(
    session: Session,
    user: User,
    *,
    remember_me: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuthTokens:
    session_id = new_session_id()
    refresh_minutes = settings.refresh_token_expire_minutes if remember_me else settings.access_token_expire_minutes * 4

    access_token = create_token(
        subject=user.id,
        role=user.role_enum,
        token_type="access",
        session_id=session_id,
        extra_claims={"email": user.email, "name": user.full_name},
    )
    refresh_token = create_token(
        subject=user.id,
        role=user.role_enum,
        token_type="refresh",
        session_id=session_id,
        expires_delta=timedelta(minutes=refresh_minutes),
    )
    refresh_payload = decode_token(refresh_token, expected_type="refresh")

    session.add(
        UserSession(
            user_id=user.id,
            session_id=session_id,
            refresh_jti=refresh_payload.jti,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500] or None,
            remember_me=remember_me,
            last_seen_at=datetime.now(UTC),
            expires_at=refresh_payload.expires_at,
        )
    )
    session.flush()

    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        session_id=session_id,
    )


def get_session(session: Session, session_id: str) -> UserSession | None:
    return session.scalar(select(UserSession).where(UserSession.session_id == session_id))


def validate_session(session: Session, session_id: str | None) -> UserSession | None:
    """Enforce revocation and idle timeout; refreshes ``last_seen_at``."""
    if not session_id:
        return None
    user_session = get_session(session, session_id)
    if user_session is None:
        raise AuthenticationError("Session not found. Please sign in again.")
    if user_session.is_revoked:
        raise AuthenticationError("Session has been signed out. Please sign in again.")

    now = datetime.now(UTC)
    if user_session.expires_at and _as_utc(user_session.expires_at) < now:
        user_session.is_revoked = True
        raise AuthenticationError("Session expired. Please sign in again.")

    idle_limit = timedelta(minutes=settings.session_idle_timeout_minutes)
    last_seen = _as_utc(user_session.last_seen_at) if user_session.last_seen_at else None
    if last_seen and not user_session.remember_me and now - last_seen > idle_limit:
        user_session.is_revoked = True
        raise AuthenticationError(
            f"Session timed out after {settings.session_idle_timeout_minutes} minutes of inactivity."
        )

    user_session.last_seen_at = now
    return user_session


def refresh_tokens(session: Session, refresh_token: str) -> tuple[User, AuthTokens]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user_session = get_session(session, payload.session_id or "")
    if user_session is None or user_session.is_revoked or user_session.refresh_jti != payload.jti:
        raise AuthenticationError("Refresh token is no longer valid. Please sign in again.")

    user = session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not available")

    # Rotate: the old session is retired and a new one issued.
    user_session.is_revoked = True
    tokens = issue_tokens(
        session,
        user,
        remember_me=user_session.remember_me,
        ip_address=user_session.ip_address,
        user_agent=user_session.user_agent,
    )
    return user, tokens


def logout(session: Session, *, user: User, session_id: str | None, all_sessions: bool = False) -> int:
    statement = select(UserSession).where(UserSession.user_id == user.id, UserSession.is_revoked.is_(False))
    if not all_sessions and session_id:
        statement = statement.where(UserSession.session_id == session_id)
    revoked = 0
    for user_session in session.scalars(statement):
        user_session.is_revoked = True
        revoked += 1
    record_audit(
        session,
        action=AuditAction.LOGOUT,
        user_id=user.id,
        actor_email=user.email,
        description="Signed out of all devices" if all_sessions else "Signed out",
        meta={"sessions_revoked": revoked},
    )
    return revoked


def request_password_reset(session: Session, email: str, *, ip_address: str | None = None) -> str | None:
    """Returns a reset token. Callers must not leak whether the email exists."""
    user = get_user_by_email(session, email)
    if user is None or not user.is_active:
        logger.info("password reset requested for unknown/inactive email")
        return None
    token = generate_password_reset_token(user.id, user.role_enum, user.hashed_password)
    record_audit(
        session,
        action=AuditAction.PASSWORD_RESET_REQUEST,
        user_id=user.id,
        actor_email=user.email,
        description="Password reset link generated",
        ip_address=ip_address,
    )
    return token


def reset_password(session: Session, *, token: str, new_password: str) -> User:
    try:
        payload = decode_token(token, expected_type="reset")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user = session.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not available")
    try:
        verify_password_reset_token(token, user.hashed_password)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    for user_session in session.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.is_revoked.is_(False))
    ):
        user_session.is_revoked = True

    record_audit(
        session,
        action=AuditAction.PASSWORD_RESET,
        user_id=user.id,
        actor_email=user.email,
        description="Password reset completed; all sessions revoked",
    )
    return user


def change_password(session: Session, *, user: User, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, user.hashed_password):
        raise AuthenticationError("Current password is incorrect")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    record_audit(
        session,
        action=AuditAction.PASSWORD_RESET,
        user_id=user.id,
        actor_email=user.email,
        description="Password changed by user",
    )
    return user


def validate_password_strength(password: str) -> None:
    from app.core.exceptions import ValidationAppError

    if len(password or "") < 10:
        raise ValidationAppError("Password must be at least 10 characters long")
    checks = [
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() for character in password),
    ]
    if sum(1 for check in checks if check) < 3:
        raise ValidationAppError(
            "Password must combine at least three of: lowercase, uppercase, digits, symbols"
        )


# ------------------------------------------------------------------ user admin
def create_user(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: UserRole | str,
    department: str | None = None,
    phone: str | None = None,
    is_active: bool = True,
    must_change_password: bool = False,
    actor: User | None = None,
) -> User:
    email = (email or "").strip().lower()
    if get_user_by_email(session, email) is not None:
        raise ConflictError(f"A user with email {email} already exists")
    validate_password_strength(password)

    user = User(
        email=email,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        role=role.value if isinstance(role, UserRole) else str(role),
        department=department,
        phone=phone,
        is_active=is_active,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.flush()
    record_audit(
        session,
        action=AuditAction.USER_CREATE,
        user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        entity_type="user",
        entity_id=user.id,
        description=f"Created {user.role} account for {user.email}",
    )
    return user


def update_user(
    session: Session,
    *,
    user_id: int,
    actor: User,
    full_name: str | None = None,
    role: UserRole | str | None = None,
    department: str | None = None,
    phone: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if user.id == actor.id and is_active is False:
        raise PermissionDeniedError("You cannot deactivate your own account")

    if full_name is not None:
        user.full_name = full_name.strip()
    if role is not None:
        user.role = role.value if isinstance(role, UserRole) else str(role)
    if department is not None:
        user.department = department
    if phone is not None:
        user.phone = phone
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            for user_session in session.scalars(
                select(UserSession).where(UserSession.user_id == user.id, UserSession.is_revoked.is_(False))
            ):
                user_session.is_revoked = True
    if password:
        validate_password_strength(password)
        user.hashed_password = hash_password(password)
        user.must_change_password = True

    record_audit(
        session,
        action=AuditAction.USER_UPDATE,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="user",
        entity_id=user.id,
        description=f"Updated account {user.email}",
    )
    return user


def list_users(session: Session, *, include_inactive: bool = True) -> list[User]:
    statement = select(User).order_by(User.full_name)
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))
    return list(session.scalars(statement))


def user_permissions(user: User) -> list[str]:
    return sorted(permissions_for(user.role_enum))


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
