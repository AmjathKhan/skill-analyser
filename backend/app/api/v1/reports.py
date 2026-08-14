"""Reports and exports."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DbSession, require_permission
from app.core.constants import AuditAction
from app.models.user import User
from app.schemas.dashboard import ReportResponse
from app.services.audit import record_audit
from app.services.reports import build_report, export_candidates_csv, export_report

router = APIRouter(tags=["Reports"])

ReportPermission = Annotated[User, Depends(require_permission("report:read"))]


@router.get("/reports", response_model=ReportResponse)
def reports(
    session: DbSession,
    _: ReportPermission,
    months: int = Query(6, ge=1, le=24),
    gap_skills: list[str] | None = Query(None, description="Skills to run gap analysis on"),
) -> ReportResponse:
    return build_report(session, gap_skills=gap_skills, months=months)


@router.get("/reports/export")
def export(
    session: DbSession,
    actor: ReportPermission,
    format: str = Query("pdf", pattern="^(pdf|csv|excel|xlsx)$"),
    months: int = Query(6, ge=1, le=24),
    gap_skills: list[str] | None = Query(None),
) -> Response:
    report = build_report(session, gap_skills=gap_skills, months=months)
    payload, media_type, filename = export_report(report, format)
    record_audit(
        session,
        action=AuditAction.REPORT_EXPORT,
        user_id=actor.id,
        actor_email=actor.email,
        description=f"Exported recruitment report as {format.upper()}",
        meta={"format": format, "bytes": len(payload)},
    )
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/candidates/export")
def export_candidates(
    session: DbSession,
    actor: ReportPermission,
    candidate_ids: list[int] | None = Query(None),
) -> Response:
    payload = export_candidates_csv(session, candidate_ids)
    record_audit(
        session,
        action=AuditAction.REPORT_EXPORT,
        user_id=actor.id,
        actor_email=actor.email,
        description="Exported candidate list as CSV",
        meta={"candidates": len(candidate_ids or [])},
    )
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="candidates.csv"'},
    )
