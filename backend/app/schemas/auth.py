"""Authentication and user management schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.constants import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    all_sessions: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    #: Returned in non-production environments so the flow is testable without SMTP.
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    email: EmailStr
    full_name: str
    role: str
    role_label: str | None = None
    department: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool
    must_change_password: bool = False
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    permissions: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    role: UserRole = UserRole.RECRUITER
    department: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool = True
    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: UserRole | None = None
    department: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    ip_address: str | None = None
    user_agent: str | None = None
    remember_me: bool
    is_revoked: bool
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


TokenResponse.model_rebuild()
