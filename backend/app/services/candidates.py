"""Candidate presentation, editing and lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, CandidateStatus
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.graph.builder import KnowledgeGraphBuilder
from app.models.audit import RecruiterNote
from app.models.candidate import Candidate
from app.models.resume import Resume
from app.models.user import User
from app.repositories import candidate_repository as repo
from app.schemas.candidate import (
    CandidateDetail,
    CandidateListItem,
    CandidateUpdate,
    CertificationRead,
    EducationRead,
    ExperienceRead,
    ProjectRead,
    RecruiterNoteRead,
    ResumeSummary,
    SkillRead,
)
from app.services.audit import record_audit

logger = get_logger(__name__)

STATUS_LABELS = {
    CandidateStatus.NEW: "New",
    CandidateStatus.PENDING_REVIEW: "Pending Review",
    CandidateStatus.IN_REVIEW: "In Review",
    CandidateStatus.SHORTLISTED: "Shortlisted",
    CandidateStatus.INTERVIEWING: "Interviewing",
    CandidateStatus.OFFERED: "Offered",
    CandidateStatus.HIRED: "Hired",
    CandidateStatus.REJECTED: "Rejected",
    CandidateStatus.ON_HOLD: "On Hold",
}


def to_list_item(candidate: Candidate) -> CandidateListItem:
    top_skills = [
        link.display_name
        for link in sorted(
            candidate.skills, key=lambda link: (not link.is_primary, -(link.confidence or 0), link.raw_text)
        )[:8]
    ]
    return CandidateListItem(
        id=candidate.id,
        uuid=candidate.uuid,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        current_title=candidate.current_title,
        current_company_name=candidate.current_company_name,
        city=candidate.city,
        country=candidate.country,
        total_experience_years=candidate.total_experience_years or 0.0,
        highest_degree=candidate.highest_degree,
        status=candidate.status,
        availability=candidate.availability,
        last_match_score=candidate.last_match_score,
        profile_completeness=candidate.profile_completeness,
        top_skills=top_skills,
        resume_count=len(candidate.resumes),
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def to_skill_read(link: Any) -> SkillRead:
    skill = link.skill
    return SkillRead(
        id=link.id,
        skill_id=link.skill_id,
        name=skill.name if skill else link.raw_text,
        category=skill.category.name if skill and skill.category else None,
        technology_stack=skill.technology_stack if skill else None,
        proficiency=link.proficiency,
        years_experience=link.years_experience,
        confidence=round(float(link.confidence or 0.0), 3),
        source=link.source,
        evidence=link.evidence,
        mention_count=link.mention_count,
        is_primary=link.is_primary,
        in_taxonomy=link.skill_id is not None,
    )


def build_timeline(candidate: Candidate) -> list[dict[str, Any]]:
    """Career timeline combining experience, education and certifications."""
    entries: list[dict[str, Any]] = []
    for experience in candidate.experiences:
        entries.append(
            {
                "type": "experience",
                "title": experience.job_title or "Role",
                "subtitle": experience.company_name,
                "start": experience.start_date.isoformat() if experience.start_date else None,
                "end": experience.end_date.isoformat() if experience.end_date else None,
                "is_current": experience.is_current,
                "detail": experience.description,
                "technologies": experience.technologies or [],
                "sort_key": experience.start_date.isoformat() if experience.start_date else "0000",
            }
        )
    for education in candidate.educations:
        entries.append(
            {
                "type": "education",
                "title": education.degree or "Education",
                "subtitle": education.institution,
                "start": f"{education.start_year}-01-01" if education.start_year else None,
                "end": f"{education.graduation_year}-01-01" if education.graduation_year else None,
                "is_current": False,
                "detail": education.field_of_study,
                "technologies": [],
                "sort_key": str(education.start_year or education.graduation_year or "0000"),
            }
        )
    for certification in candidate.certifications:
        entries.append(
            {
                "type": "certification",
                "title": certification.name,
                "subtitle": certification.issuer,
                "start": certification.issue_date.isoformat() if certification.issue_date else None,
                "end": certification.expiry_date.isoformat() if certification.expiry_date else None,
                "is_current": False,
                "detail": certification.credential_id,
                "technologies": [],
                "sort_key": certification.issue_date.isoformat() if certification.issue_date else "0000",
            }
        )
    entries.sort(key=lambda entry: entry["sort_key"], reverse=True)
    for entry in entries:
        entry.pop("sort_key", None)
    return entries


def to_resume_summary(resume: Resume) -> ResumeSummary:
    return ResumeSummary(
        id=resume.id,
        uuid=resume.uuid,
        original_filename=resume.original_filename,
        extension=resume.extension,
        file_size=resume.file_size,
        status=resume.status,
        page_count=resume.page_count,
        word_count=resume.word_count,
        ocr_used=resume.ocr_used,
        extraction_backend=resume.extraction_backend,
        parse_error=resume.parse_error,
        duplicate_of_id=resume.duplicate_of_id,
        parse_duration_ms=resume.parse_duration_ms,
        created_at=resume.created_at,
        uploaded_by_id=resume.uploaded_by_id,
        uploaded_by_name=resume.uploaded_by.full_name if resume.uploaded_by else None,
        candidate_id=resume.candidate_id,
        download_url=f"/api/resume/{resume.id}/download",
    )


def to_detail(candidate: Candidate) -> CandidateDetail:
    base = to_list_item(candidate).model_dump()
    return CandidateDetail(
        **base,
        address=candidate.address,
        state=candidate.state,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        portfolio_url=candidate.portfolio_url,
        headline=candidate.headline,
        notice_period_days=candidate.notice_period_days,
        expected_ctc=candidate.expected_ctc,
        languages=[str(language) for language in (candidate.languages or [])],
        tags=[str(tag) for tag in (candidate.tags or [])],
        ai_summary=candidate.ai_summary,
        ai_highlights=[str(item) for item in (candidate.ai_highlights or [])],
        graph_synced_at=candidate.graph_synced_at,
        owner_id=candidate.owner_id,
        owner_name=candidate.owner.full_name if candidate.owner else None,
        skills=[
            to_skill_read(link)
            for link in sorted(
                candidate.skills, key=lambda link: (not link.is_primary, -(link.confidence or 0))
            )
        ],
        experiences=[
            ExperienceRead(
                id=experience.id,
                company_name=experience.company_name,
                job_title=experience.job_title,
                location=experience.location,
                start_date=experience.start_date,
                end_date=experience.end_date,
                is_current=experience.is_current,
                duration_months=experience.duration_months,
                description=experience.description,
                technologies=[str(item) for item in (experience.technologies or [])],
            )
            for experience in candidate.experiences
        ],
        educations=[EducationRead.model_validate(education) for education in candidate.educations],
        projects=[
            ProjectRead(
                id=project.id,
                name=project.name,
                role=project.role,
                description=project.description,
                technologies=[str(item) for item in (project.technologies or [])],
                url=project.url,
            )
            for project in candidate.projects
        ],
        certifications=[CertificationRead.model_validate(item) for item in candidate.certifications],
        notes=[
            RecruiterNoteRead(
                id=note.id,
                content=note.content,
                rating=note.rating,
                is_private=note.is_private,
                author_id=note.author_id,
                author_name=note.author.full_name if note.author else None,
                created_at=note.created_at,
            )
            for note in sorted(candidate.notes, key=lambda note: note.created_at, reverse=True)
        ],
        resumes=[to_resume_summary(resume) for resume in sorted(candidate.resumes, key=lambda item: item.created_at, reverse=True)],
        timeline=build_timeline(candidate),
    )


def require_candidate(session: Session, candidate_id: int) -> Candidate:
    candidate = repo.get_candidate(session, candidate_id)
    if candidate is None:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    return candidate


def update_candidate(session: Session, *, candidate_id: int, payload: CandidateUpdate, actor: User) -> Candidate:
    candidate = require_candidate(session, candidate_id)
    changes: dict[str, Any] = {}

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field == "status":
            value = value.value if hasattr(value, "value") else value
        current = getattr(candidate, field, None)
        if current != value:
            changes[field] = {"from": current, "to": value}
            setattr(candidate, field, value)

    if changes:
        record_audit(
            session,
            action=AuditAction.CANDIDATE_UPDATE,
            user_id=actor.id,
            actor_email=actor.email,
            entity_type="candidate",
            entity_id=candidate.id,
            description=f"Updated {', '.join(changes)} for {candidate.full_name}",
            meta={"changes": {key: {"from": str(v["from"]), "to": str(v["to"])} for key, v in changes.items()}},
        )
        if "full_name" in changes or "current_company_name" in changes or "total_experience_years" in changes:
            KnowledgeGraphBuilder(session).sync_candidate(candidate, replace=False)
    return candidate


def change_status(
    session: Session, *, candidate_id: int, status: CandidateStatus, reason: str | None, actor: User
) -> Candidate:
    candidate = require_candidate(session, candidate_id)
    previous = candidate.status
    candidate.status = status.value
    record_audit(
        session,
        action=AuditAction.CANDIDATE_STATUS_CHANGE,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="candidate",
        entity_id=candidate.id,
        description=f"Status changed {previous} -> {status.value}" + (f" ({reason})" if reason else ""),
        meta={"from": previous, "to": status.value, "reason": reason},
    )
    KnowledgeGraphBuilder(session).sync_candidate(candidate, replace=False)
    return candidate


def delete_candidate(session: Session, *, candidate_id: int, actor: User, hard: bool = False) -> None:
    candidate = require_candidate(session, candidate_id)
    if hard and not actor.is_admin:
        raise PermissionDeniedError("Only an HR Admin can permanently delete a candidate")

    from app.ai.vector_store import get_vector_store

    get_vector_store().delete_for_candidate(session, candidate.id)
    KnowledgeGraphBuilder(session).remove_candidate(candidate.id)

    if hard:
        from app.services import storage

        for resume in candidate.resumes:
            if not resume.duplicate_of_id:
                storage.delete_resume(resume.storage_path)
        session.delete(candidate)
    else:
        candidate.is_deleted = True
        candidate.graph_synced_at = None

    record_audit(
        session,
        action=AuditAction.CANDIDATE_DELETE,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="candidate",
        entity_id=candidate_id,
        description=("Permanently deleted " if hard else "Archived ") + f"candidate #{candidate_id}",
        meta={"hard_delete": hard},
    )


def add_note(
    session: Session, *, candidate_id: int, content: str, rating: int | None, is_private: bool, actor: User
) -> RecruiterNote:
    candidate = require_candidate(session, candidate_id)
    note = RecruiterNote(
        candidate_id=candidate.id,
        author_id=actor.id,
        content=content.strip(),
        rating=rating,
        is_private=is_private,
    )
    session.add(note)
    session.flush()
    record_audit(
        session,
        action=AuditAction.NOTE_CREATE,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="candidate",
        entity_id=candidate.id,
        description=f"Added a note on {candidate.full_name}",
    )
    return note


def visible_notes(candidate: Candidate, actor: User) -> list[RecruiterNote]:
    return [
        note
        for note in candidate.notes
        if not note.is_private or note.author_id == actor.id or actor.is_admin
    ]


def touch_graph_sync(candidate: Candidate) -> None:
    candidate.graph_synced_at = datetime.now(UTC)
