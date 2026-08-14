"""Knowledge graph endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_permission
from app.models.user import User
from app.schemas.graph import (
    GraphBuildRequest,
    GraphBuildResponse,
    GraphStatsResponse,
    GraphView,
    SkillGraphResponse,
)
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])

ReadPermission = Annotated[User, Depends(require_permission("graph:read"))]
BuildPermission = Annotated[User, Depends(require_permission("graph:build"))]


@router.post("/build", response_model=GraphBuildResponse)
def build_graph(request: GraphBuildRequest, session: DbSession, actor: BuildPermission) -> GraphBuildResponse:
    """(Re)build the knowledge graph from PostgreSQL into the active graph backend."""
    return graph_service.build_graph(session, request, user_id=actor.id)


@router.get("/candidate/{candidate_id}", response_model=GraphView)
def candidate_graph(
    candidate_id: int,
    session: DbSession,
    _: ReadPermission,
    depth: int = Query(2, ge=1, le=4),
    limit: int = Query(250, ge=10, le=1000),
) -> GraphView:
    return graph_service.candidate_view(session, candidate_id, depth=depth, limit=limit)


@router.get("/skills", response_model=SkillGraphResponse)
def skills_graph(
    session: DbSession,
    _: ReadPermission,
    limit: int = Query(200, ge=1, le=1000),
    include_view: bool = False,
) -> SkillGraphResponse:
    return graph_service.skills_graph(session, limit=limit, include_view=include_view)


@router.get("/skill/{skill_name}", response_model=GraphView)
def skill_graph(
    skill_name: str,
    session: DbSession,
    _: ReadPermission,
    depth: int = Query(2, ge=1, le=4),
    limit: int = Query(200, ge=10, le=1000),
) -> GraphView:
    return graph_service.skill_view(session, skill_name, depth=depth, limit=limit)


@router.get("/overview", response_model=GraphView)
def graph_overview(
    session: DbSession,
    _: ReadPermission,
    limit: int = Query(220, ge=20, le=1000),
    candidates: int = Query(25, ge=1, le=200),
) -> GraphView:
    return graph_service.overview_view(session, limit=limit, candidate_limit=candidates)


@router.get("/stats", response_model=GraphStatsResponse)
def graph_stats(session: DbSession, _: ReadPermission) -> GraphStatsResponse:
    return graph_service.graph_stats(session)
