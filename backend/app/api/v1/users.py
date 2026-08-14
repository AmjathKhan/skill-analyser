"""User management (HR Admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.api.v1.auth import to_user_read
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.auth import UserCreate, UserRead, UserUpdate
from app.schemas.common import MessageResponse
from app.services import auth as auth_service
from app.services.audit import list_audit_logs

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=list[UserRead])
def list_users(session: DbSession, _: AdminUser, include_inactive: bool = True) -> list[UserRead]:
    return [to_user_read(user) for user in auth_service.list_users(session, include_inactive=include_inactive)]


@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, session: DbSession, actor: AdminUser) -> UserRead:
    user = auth_service.create_user(
        session,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role=payload.role,
        department=payload.department,
        phone=payload.phone,
        is_active=payload.is_active,
        must_change_password=payload.must_change_password,
        actor=actor,
    )
    return to_user_read(user)


@router.get("/audit/logs", response_model=dict)
def audit_logs(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = None,
    user_id: int | None = None,
) -> dict:
    rows, total = list_audit_logs(session, page=page, page_size=page_size, action=action, user_id=user_id)
    return {
        "items": [
            {
                "id": entry.id,
                "action": entry.action,
                "actor": entry.user.full_name if entry.user else entry.actor_email or "System",
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "description": entry.description,
                "ip_address": entry.ip_address,
                "status": entry.status,
                "created_at": entry.created_at.isoformat(),
                "meta": entry.meta,
            }
            for entry in rows
        ],
        "meta": {"page": page, "page_size": page_size, "total": total},
    }


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, session: DbSession, _: AdminUser) -> UserRead:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return to_user_read(user)


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, session: DbSession, actor: AdminUser) -> UserRead:
    user = auth_service.update_user(
        session,
        user_id=user_id,
        actor=actor,
        full_name=payload.full_name,
        role=payload.role,
        department=payload.department,
        phone=payload.phone,
        is_active=payload.is_active,
        password=payload.password,
    )
    return to_user_read(user)


@router.delete("/{user_id}", response_model=MessageResponse)
def deactivate_user(user_id: int, session: DbSession, actor: AdminUser) -> MessageResponse:
    auth_service.update_user(session, user_id=user_id, actor=actor, is_active=False)
    return MessageResponse(message="User deactivated", detail="Active sessions were revoked.")
