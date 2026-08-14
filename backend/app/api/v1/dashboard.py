"""Dashboard endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permission
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import build_dashboard

router = APIRouter(tags=["Dashboard"])

ReadPermission = Annotated[User, Depends(require_permission("candidate:read"))]


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(session: DbSession, _: ReadPermission) -> DashboardResponse:
    """Cards, charts, recent activity and AI recommendations for the landing page."""
    return build_dashboard(session)
