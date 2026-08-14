"""Audit logging and the recent-activity feed."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import AuditAction
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.user import User

logger = get_logger(__name__)


def record_audit(
    session: Session,
    *,
    action: AuditAction | str,
    user_id: int | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status: str = "success",
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        actor_email=actor_email,
        action=action.value if isinstance(action, AuditAction) else str(action),
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
        status=status,
        meta=meta,
    )
    session.add(entry)
    session.flush()
    return entry


def recent_activity(session: Session, *, limit: int = 20, actions: list[str] | None = None) -> list[AuditLog]:
    statement = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    if actions:
        statement = statement.where(AuditLog.action.in_(actions))
    return list(session.scalars(statement))


def actor_label(entry: AuditLog) -> str:
    if entry.user is not None:
        return entry.user.full_name
    if entry.actor_email:
        return entry.actor_email
    return "System"


def list_audit_logs(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
    user_id: int | None = None,
) -> tuple[list[AuditLog], int]:
    from sqlalchemy import func

    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if user_id:
        filters.append(AuditLog.user_id == user_id)

    total = session.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0
    rows = list(
        session.scalars(
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return rows, total


def user_display(session: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = session.get(User, user_id)
    return user.full_name if user else None
