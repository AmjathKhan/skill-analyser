"""FastAPI dependencies: authentication, RBAC and rate limiting."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, PermissionDeniedError, RateLimitError
from app.core.rate_limit import get_rate_limiter
from app.core.security import TokenError, decode_token, role_has_permission
from app.db.session import get_db
from app.models.user import User
from app.services.auth import validate_session

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token issued by POST /api/login")

DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_current_user(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user = session.get(User, payload.user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists")
    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    validate_session(session, payload.session_id)

    request.state.user_id = user.id
    request.state.session_id = payload.session_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if not role_has_permission(user.role_enum, permission):
            raise PermissionDeniedError(
                f"Your role ({UserRole(user.role).label}) does not allow '{permission}'"
            )
        return user

    return dependency


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    allowed = {role.value for role in roles}

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError("You do not have access to this resource")
        return user

    return dependency


def rate_limit(
    key: str, *, limit: int | None = None, window: int | None = None
) -> Callable[[Request], None]:
    """Per-endpoint sliding-window limiter keyed by client IP."""

    def dependency(request: Request) -> None:
        verdict = get_rate_limiter().check(
            f"{key}:{client_ip(request)}",
            limit=limit or settings.rate_limit_requests,
            window=window or settings.rate_limit_window_seconds,
        )
        if not verdict.allowed:
            raise RateLimitError(
                f"Too many requests. Retry in {verdict.retry_after} second(s).",
                details={"retry_after": verdict.retry_after},
            )

    return dependency


LoginRateLimit = Depends(
    rate_limit(
        "login",
        limit=settings.login_rate_limit_requests,
        window=settings.login_rate_limit_window_seconds,
    )
)

AiRateLimit = Depends(rate_limit("ai", limit=max(30, settings.rate_limit_requests // 4), window=60))

AdminUser = Annotated[User, Depends(require_roles(UserRole.HR_ADMIN))]
