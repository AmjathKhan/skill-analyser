"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession, LoginRateLimit, client_ip
from app.core.config import Environment, settings
from app.core.constants import UserRole
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SessionRead,
    TokenResponse,
    UserRead,
)
from app.schemas.common import MessageResponse
from app.services import auth as auth_service

router = APIRouter(tags=["Authentication"])


def to_user_read(user) -> UserRead:
    return UserRead(
        id=user.id,
        uuid=user.uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        role_label=UserRole(user.role).label,
        department=user.department,
        phone=user.phone,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        permissions=auth_service.user_permissions(user),
    )


@router.post("/login", response_model=TokenResponse, dependencies=[LoginRateLimit])
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    """Authenticate and receive an access + refresh token pair."""
    user, tokens = auth_service.authenticate(
        session,
        email=payload.email,
        password=payload.password,
        remember_me=payload.remember_me,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=to_user_read(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, session: DbSession) -> TokenResponse:
    user, tokens = auth_service.refresh_tokens(session, payload.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=to_user_read(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, request: Request, session: DbSession, user: CurrentUser) -> MessageResponse:
    revoked = auth_service.logout(
        session,
        user=user,
        session_id=getattr(request.state, "session_id", None),
        all_sessions=payload.all_sessions,
    )
    return MessageResponse(message="Signed out", detail=f"{revoked} session(s) revoked")


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return to_user_read(user)


@router.get("/me/sessions", response_model=list[SessionRead])
def my_sessions(user: CurrentUser) -> list[SessionRead]:
    return [SessionRead.model_validate(item) for item in sorted(user.sessions, key=lambda s: s.created_at, reverse=True)]


@router.post("/forgot-password", response_model=ForgotPasswordResponse, dependencies=[LoginRateLimit])
def forgot_password(payload: ForgotPasswordRequest, request: Request, session: DbSession) -> ForgotPasswordResponse:
    """Always returns success so the endpoint cannot be used to enumerate accounts."""
    token = auth_service.request_password_reset(session, payload.email, ip_address=client_ip(request))
    expose_token = settings.environment is not Environment.production
    return ForgotPasswordResponse(
        message="If the email exists, a password reset link has been sent.",
        reset_token=token if (expose_token and token) else None,
    )


@router.post("/reset-password", response_model=MessageResponse, dependencies=[LoginRateLimit])
def reset_password(payload: ResetPasswordRequest, session: DbSession) -> MessageResponse:
    auth_service.reset_password(session, token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="Password updated", detail="All existing sessions were signed out.")


@router.post("/change-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
def change_password(payload: ChangePasswordRequest, session: DbSession, user: CurrentUser) -> MessageResponse:
    auth_service.change_password(
        session, user=user, current_password=payload.current_password, new_password=payload.new_password
    )
    return MessageResponse(message="Password changed")
