"""Candidate search endpoints (semantic / keyword / graph / skill / hybrid)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AiRateLimit, DbSession, require_permission
from app.core.constants import AuditAction
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResponse, SuggestResponse
from app.services.audit import record_audit
from app.services.graph_service import ensure_hydrated
from app.services.search import SearchService

router = APIRouter(tags=["Search"])

SearchPermission = Annotated[User, Depends(require_permission("search:run"))]


@router.post("/search", response_model=SearchResponse, dependencies=[AiRateLimit])
def search(request: SearchRequest, session: DbSession, actor: SearchPermission) -> SearchResponse:
    """Search candidates. Example query: ``Python React PostgreSQL FastAPI 5 years``."""
    ensure_hydrated(session)
    response = SearchService(session).search(request)
    record_audit(
        session,
        action=AuditAction.SEARCH,
        user_id=actor.id,
        actor_email=actor.email,
        description=f"[{request.mode}] {request.query[:180]}" if request.query else f"[{request.mode}] filtered search",
        meta={
            "mode": request.mode,
            "results": response.total,
            "interpreted_skills": response.interpreted_skills,
            "duration_ms": response.duration_ms,
        },
    )
    return response


@router.get("/search/suggest", response_model=SuggestResponse)
def suggest(
    session: DbSession,
    _: SearchPermission,
    q: str = Query(..., min_length=2, max_length=80),
    limit: int = Query(8, ge=1, le=25),
) -> SuggestResponse:
    return SearchService(session).suggest(q, limit=limit)
