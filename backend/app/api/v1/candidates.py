"""Candidate list, detail, editing and notes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_permission
from app.models.user import User
from app.repositories import candidate_repository as repo
from app.schemas.candidate import (
    CandidateDetail,
    CandidateFilters,
    CandidateListItem,
    CandidateStatusUpdate,
    CandidateUpdate,
    RecruiterNoteCreate,
    RecruiterNoteRead,
    SimilarCandidate,
)
from app.schemas.common import MessageResponse, Page, PageMeta
from app.schemas.matching import CandidateMatch, MatchCriteria
from app.services import candidates as candidate_service
from app.services.matching import MatchingEngine

router = APIRouter(tags=["Candidates"])

ReadPermission = Annotated[User, Depends(require_permission("candidate:read"))]
WritePermission = Annotated[User, Depends(require_permission("candidate:write"))]
DeletePermission = Annotated[User, Depends(require_permission("candidate:delete"))]


@router.get("/candidates", response_model=Page[CandidateListItem])
def list_candidates(
    session: DbSession,
    _: ReadPermission,
    search: str | None = Query(None, description="Free text over name, email, title, company and skills"),
    status: list[str] | None = Query(None),
    skills: list[str] | None = Query(None, description="Repeat to require multiple skills"),
    min_experience: float | None = Query(None, ge=0, le=60),
    max_experience: float | None = Query(None, ge=0, le=60),
    location: str | None = None,
    company: str | None = None,
    education: str | None = None,
    certification: str | None = None,
    technology: str | None = None,
    availability: str | None = None,
    owner_id: int | None = None,
    uploaded_after: datetime | None = None,
    sort_by: str = Query("created_at", description="created_at | name | experience | ai_score | status"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[CandidateListItem]:
    filters = CandidateFilters(
        search=search,
        status=status,
        skills=skills,
        min_experience=min_experience,
        max_experience=max_experience,
        location=location,
        company=company,
        education=education,
        certification=certification,
        technology=technology,
        availability=availability,
        owner_id=owner_id,
        uploaded_after=uploaded_after,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    rows, total = repo.list_candidates(session, filters)
    return Page[CandidateListItem](
        items=[candidate_service.to_list_item(candidate) for candidate in rows],
        meta=PageMeta.build(page=page, page_size=page_size, total=total),
    )


@router.get("/candidate/{candidate_id}", response_model=CandidateDetail)
def get_candidate(candidate_id: int, session: DbSession, actor: ReadPermission) -> CandidateDetail:
    candidate = candidate_service.require_candidate(session, candidate_id)
    detail = candidate_service.to_detail(candidate)
    visible = {note.id for note in candidate_service.visible_notes(candidate, actor)}
    detail.notes = [note for note in detail.notes if note.id in visible]
    return detail


@router.put("/candidate/{candidate_id}", response_model=CandidateDetail)
def update_candidate(
    candidate_id: int, payload: CandidateUpdate, session: DbSession, actor: WritePermission
) -> CandidateDetail:
    candidate = candidate_service.update_candidate(
        session, candidate_id=candidate_id, payload=payload, actor=actor
    )
    return candidate_service.to_detail(candidate)


@router.patch("/candidate/{candidate_id}/status", response_model=CandidateDetail)
def change_status(
    candidate_id: int, payload: CandidateStatusUpdate, session: DbSession, actor: WritePermission
) -> CandidateDetail:
    candidate = candidate_service.change_status(
        session, candidate_id=candidate_id, status=payload.status, reason=payload.reason, actor=actor
    )
    return candidate_service.to_detail(candidate)


@router.delete("/candidate/{candidate_id}", response_model=MessageResponse)
def delete_candidate(
    candidate_id: int,
    session: DbSession,
    actor: DeletePermission,
    hard: bool = Query(False, description="Permanently delete (HR Admin only)"),
) -> MessageResponse:
    candidate_service.delete_candidate(session, candidate_id=candidate_id, actor=actor, hard=hard)
    return MessageResponse(
        message="Candidate permanently deleted" if hard else "Candidate archived",
        detail="Embeddings and graph nodes were removed.",
    )


@router.post("/candidate/{candidate_id}/notes", response_model=RecruiterNoteRead, status_code=201)
def add_note(
    candidate_id: int, payload: RecruiterNoteCreate, session: DbSession, actor: WritePermission
) -> RecruiterNoteRead:
    note = candidate_service.add_note(
        session,
        candidate_id=candidate_id,
        content=payload.content,
        rating=payload.rating,
        is_private=payload.is_private,
        actor=actor,
    )
    return RecruiterNoteRead(
        id=note.id,
        content=note.content,
        rating=note.rating,
        is_private=note.is_private,
        author_id=note.author_id,
        author_name=actor.full_name,
        created_at=note.created_at,
    )


@router.post("/candidate/{candidate_id}/score", response_model=CandidateMatch)
def score_candidate(
    candidate_id: int, criteria: MatchCriteria, session: DbSession, _: ReadPermission
) -> CandidateMatch:
    """Score a single candidate against ad-hoc criteria (profile page AI panel)."""
    candidate_service.require_candidate(session, candidate_id)
    engine = MatchingEngine(session)
    match = engine.score_single(candidate_id, criteria)
    if match is None:
        from app.core.exceptions import ValidationAppError

        raise ValidationAppError("Could not score this candidate with the supplied criteria")
    return match


@router.get("/candidate/{candidate_id}/similar", response_model=list[SimilarCandidate])
def similar_candidates(
    candidate_id: int, session: DbSession, _: ReadPermission, limit: int = Query(5, ge=1, le=25)
) -> list[SimilarCandidate]:
    from app.ai.graph_rag import GraphRAGEngine
    from app.services.graph_service import ensure_hydrated

    candidate_service.require_candidate(session, candidate_id)
    ensure_hydrated(session)
    peers = GraphRAGEngine(session).similar_candidates(candidate_id, limit=limit)
    return [SimilarCandidate.model_validate(peer) for peer in peers]
