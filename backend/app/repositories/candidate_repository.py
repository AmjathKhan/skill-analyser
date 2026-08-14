"""Query layer for candidates and the aggregates behind dashboards/reports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai.text_utils import normalize_key, tokenize
from app.core.constants import CandidateStatus, ResumeStatus
from app.models.ai import MatchRun
from app.models.candidate import (
    Candidate,
    CandidateSkill,
    Certification,
    Education,
    Experience,
    Project,
)
from app.models.resume import Resume
from app.models.skill import Skill, SkillCategory
from app.schemas.candidate import CandidateFilters

SORTABLE_COLUMNS = {
    "created_at": Candidate.created_at,
    "updated_at": Candidate.updated_at,
    "name": Candidate.full_name,
    "full_name": Candidate.full_name,
    "experience": Candidate.total_experience_years,
    "total_experience_years": Candidate.total_experience_years,
    "ai_score": Candidate.last_match_score,
    "last_match_score": Candidate.last_match_score,
    "status": Candidate.status,
    "upload_date": Candidate.created_at,
}

DETAIL_LOADERS = (
    selectinload(Candidate.skills).selectinload(CandidateSkill.skill).selectinload(Skill.category),
    selectinload(Candidate.experiences),
    selectinload(Candidate.educations),
    selectinload(Candidate.projects),
    selectinload(Candidate.certifications),
    selectinload(Candidate.resumes),
    selectinload(Candidate.notes),
    selectinload(Candidate.owner),
)


def get_candidate(session: Session, candidate_id: int, *, with_details: bool = True) -> Candidate | None:
    statement = select(Candidate).where(Candidate.id == candidate_id, Candidate.is_deleted.is_(False))
    if with_details:
        statement = statement.options(*DETAIL_LOADERS)
    return session.scalar(statement)


def get_candidate_by_uuid(session: Session, candidate_uuid: str, *, with_details: bool = True) -> Candidate | None:
    statement = select(Candidate).where(Candidate.uuid == candidate_uuid, Candidate.is_deleted.is_(False))
    if with_details:
        statement = statement.options(*DETAIL_LOADERS)
    return session.scalar(statement)


def _search_terms(search: str) -> list[str]:
    """Split free text into searchable terms, keeping the phrase for single words.

    Multi word input is matched term by term so ``"python kubernetes"`` still finds
    candidates whose skills are stored as separate rows.
    """
    phrase = search.strip().lower()
    if not phrase:
        return []
    words = tokenize(phrase)
    if len(words) <= 1:
        return [phrase]
    return words[:8]


def _search_clause(term: str) -> Any:
    like = f"%{term}%"
    return or_(
        func.lower(Candidate.full_name).like(like),
        func.lower(func.coalesce(Candidate.email, "")).like(like),
        func.lower(func.coalesce(Candidate.current_title, "")).like(like),
        func.lower(func.coalesce(Candidate.current_company_name, "")).like(like),
        func.lower(func.coalesce(Candidate.headline, "")).like(like),
        Candidate.id.in_(
            select(CandidateSkill.candidate_id).where(
                func.lower(CandidateSkill.normalized_name).like(f"%{normalize_key(term)}%")
            )
        ),
    )


def _apply_filters(statement: Select[Any], filters: CandidateFilters) -> Select[Any]:
    statement = statement.where(Candidate.is_deleted.is_(False))

    if filters.search:
        clauses = [_search_clause(term) for term in _search_terms(filters.search)]
        if clauses:
            statement = statement.where(
                or_(*clauses) if filters.search_mode == "any" else and_(*clauses)
            )

    if filters.status:
        statement = statement.where(Candidate.status.in_([status.lower() for status in filters.status]))

    if filters.skills:
        for skill_name in filters.skills:
            normalized = normalize_key(skill_name)
            statement = statement.where(
                Candidate.id.in_(
                    select(CandidateSkill.candidate_id)
                    .outerjoin(Skill, Skill.id == CandidateSkill.skill_id)
                    .where(
                        or_(
                            CandidateSkill.normalized_name == normalized,
                            Skill.normalized_name == normalized,
                        )
                    )
                )
            )

    if filters.min_experience is not None:
        statement = statement.where(Candidate.total_experience_years >= filters.min_experience)
    if filters.max_experience is not None:
        statement = statement.where(Candidate.total_experience_years <= filters.max_experience)

    if filters.location:
        term = f"%{filters.location.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(func.coalesce(Candidate.city, "")).like(term),
                func.lower(func.coalesce(Candidate.country, "")).like(term),
                func.lower(func.coalesce(Candidate.state, "")).like(term),
                func.lower(func.coalesce(Candidate.address, "")).like(term),
            )
        )

    if filters.company:
        term = f"%{filters.company.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(func.coalesce(Candidate.current_company_name, "")).like(term),
                Candidate.id.in_(
                    select(Experience.candidate_id).where(func.lower(Experience.company_name).like(term))
                ),
            )
        )

    if filters.education:
        term = f"%{filters.education.strip().lower()}%"
        statement = statement.where(
            Candidate.id.in_(
                select(Education.candidate_id).where(
                    or_(
                        func.lower(func.coalesce(Education.degree, "")).like(term),
                        func.lower(func.coalesce(Education.institution, "")).like(term),
                        func.lower(func.coalesce(Education.field_of_study, "")).like(term),
                    )
                )
            )
        )

    if filters.certification:
        term = f"%{filters.certification.strip().lower()}%"
        statement = statement.where(
            Candidate.id.in_(
                select(Certification.candidate_id).where(
                    or_(
                        func.lower(Certification.name).like(term),
                        func.lower(func.coalesce(Certification.issuer, "")).like(term),
                    )
                )
            )
        )

    if filters.technology:
        normalized = normalize_key(filters.technology)
        term = f"%{filters.technology.strip().lower()}%"
        statement = statement.where(
            or_(
                Candidate.id.in_(
                    select(CandidateSkill.candidate_id)
                    .join(Skill, Skill.id == CandidateSkill.skill_id)
                    .where(
                        or_(
                            func.lower(func.coalesce(Skill.technology_stack, "")).like(term),
                            Skill.normalized_name == normalized,
                        )
                    )
                ),
                Candidate.id.in_(
                    select(Project.candidate_id).where(func.lower(func.coalesce(Project.description, "")).like(term))
                ),
            )
        )

    if filters.candidate_ids is not None:
        statement = statement.where(Candidate.id.in_(filters.candidate_ids or [-1]))
    if filters.availability:
        statement = statement.where(func.lower(func.coalesce(Candidate.availability, "")) == filters.availability.lower())
    if filters.owner_id:
        statement = statement.where(Candidate.owner_id == filters.owner_id)
    if filters.uploaded_after:
        statement = statement.where(Candidate.created_at >= filters.uploaded_after)

    return statement


def list_candidates(session: Session, filters: CandidateFilters) -> tuple[list[Candidate], int]:
    base = _apply_filters(select(Candidate.id), filters)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    column = SORTABLE_COLUMNS.get(filters.sort_by, Candidate.created_at)
    order = column.desc() if filters.sort_dir.lower() == "desc" else column.asc()

    statement = (
        _apply_filters(select(Candidate), filters)
        .options(
            selectinload(Candidate.skills).selectinload(CandidateSkill.skill),
            selectinload(Candidate.resumes),
        )
        .order_by(order, Candidate.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return list(session.scalars(statement).unique()), total


def candidates_by_ids(session: Session, ids: Sequence[int], *, with_details: bool = True) -> list[Candidate]:
    if not ids:
        return []
    statement = select(Candidate).where(Candidate.id.in_(list(ids)), Candidate.is_deleted.is_(False))
    if with_details:
        statement = statement.options(*DETAIL_LOADERS)
    return list(session.scalars(statement).unique())


# ------------------------------------------------------------------- aggregates
def count_candidates(session: Session, *, status: str | None = None) -> int:
    statement = select(func.count(Candidate.id)).where(Candidate.is_deleted.is_(False))
    if status:
        statement = statement.where(Candidate.status == status)
    return session.scalar(statement) or 0


def count_resumes(session: Session, *, status: str | None = None, since: datetime | None = None) -> int:
    statement = select(func.count(Resume.id))
    if status:
        statement = statement.where(Resume.status == status)
    if since:
        statement = statement.where(Resume.created_at >= since)
    return session.scalar(statement) or 0


def status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Candidate.status, func.count(Candidate.id))
        .where(Candidate.is_deleted.is_(False))
        .group_by(Candidate.status)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def top_skills(session: Session, *, limit: int = 12) -> list[tuple[str, int, str | None]]:
    rows = session.execute(
        select(
            func.coalesce(Skill.name, CandidateSkill.raw_text).label("name"),
            func.count(func.distinct(CandidateSkill.candidate_id)).label("total"),
            SkillCategory.name,
        )
        .select_from(CandidateSkill)
        .join(Candidate, and_(Candidate.id == CandidateSkill.candidate_id, Candidate.is_deleted.is_(False)))
        .outerjoin(Skill, Skill.id == CandidateSkill.skill_id)
        .outerjoin(SkillCategory, SkillCategory.id == Skill.category_id)
        .group_by(func.coalesce(Skill.name, CandidateSkill.raw_text), SkillCategory.name)
        .order_by(func.count(func.distinct(CandidateSkill.candidate_id)).desc())
        .limit(limit)
    ).all()
    return [(name, int(total), category) for name, total, category in rows]


def technology_distribution(session: Session, *, limit: int = 10) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Skill.technology_stack, func.count(func.distinct(CandidateSkill.candidate_id)))
        .select_from(CandidateSkill)
        .join(Skill, Skill.id == CandidateSkill.skill_id)
        .join(Candidate, and_(Candidate.id == CandidateSkill.candidate_id, Candidate.is_deleted.is_(False)))
        .where(Skill.technology_stack.isnot(None))
        .group_by(Skill.technology_stack)
        .order_by(func.count(func.distinct(CandidateSkill.candidate_id)).desc())
        .limit(limit)
    ).all()
    return [(stack, int(total)) for stack, total in rows if stack]


def category_distribution(session: Session, *, limit: int = 12) -> list[tuple[str, int]]:
    rows = session.execute(
        select(SkillCategory.name, func.count(func.distinct(CandidateSkill.candidate_id)))
        .select_from(CandidateSkill)
        .join(Skill, Skill.id == CandidateSkill.skill_id)
        .join(SkillCategory, SkillCategory.id == Skill.category_id)
        .join(Candidate, and_(Candidate.id == CandidateSkill.candidate_id, Candidate.is_deleted.is_(False)))
        .group_by(SkillCategory.name)
        .order_by(func.count(func.distinct(CandidateSkill.candidate_id)).desc())
        .limit(limit)
    ).all()
    return [(name, int(total)) for name, total in rows]


EXPERIENCE_BUCKETS = (
    ("0-1 yrs", 0.0, 1.0),
    ("1-3 yrs", 1.0, 3.0),
    ("3-5 yrs", 3.0, 5.0),
    ("5-8 yrs", 5.0, 8.0),
    ("8-12 yrs", 8.0, 12.0),
    ("12+ yrs", 12.0, 100.0),
)


def experience_distribution(session: Session) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for label, low, high in EXPERIENCE_BUCKETS:
        count = (
            session.scalar(
                select(func.count(Candidate.id)).where(
                    Candidate.is_deleted.is_(False),
                    Candidate.total_experience_years >= low,
                    Candidate.total_experience_years < high,
                )
            )
            or 0
        )
        result.append((label, count))
    return result


def hiring_trends(session: Session, *, months: int = 6) -> list[tuple[str, int, int, int, int]]:
    """(period, uploads, candidates, shortlisted, rejected) for the last N months."""
    today = date.today()
    periods: list[tuple[str, datetime, datetime]] = []
    year, month = today.year, today.month
    for _ in range(months):
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=UTC)
        periods.append((f"{start:%b %Y}", start, end))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    periods.reverse()

    output: list[tuple[str, int, int, int, int]] = []
    for label, start, end in periods:
        uploads = (
            session.scalar(
                select(func.count(Resume.id)).where(Resume.created_at >= start, Resume.created_at < end)
            )
            or 0
        )
        candidates = (
            session.scalar(
                select(func.count(Candidate.id)).where(
                    Candidate.created_at >= start, Candidate.created_at < end, Candidate.is_deleted.is_(False)
                )
            )
            or 0
        )
        shortlisted = (
            session.scalar(
                select(func.count(Candidate.id)).where(
                    Candidate.updated_at >= start,
                    Candidate.updated_at < end,
                    Candidate.status == CandidateStatus.SHORTLISTED.value,
                    Candidate.is_deleted.is_(False),
                )
            )
            or 0
        )
        rejected = (
            session.scalar(
                select(func.count(Candidate.id)).where(
                    Candidate.updated_at >= start,
                    Candidate.updated_at < end,
                    Candidate.status == CandidateStatus.REJECTED.value,
                    Candidate.is_deleted.is_(False),
                )
            )
            or 0
        )
        output.append((label, uploads, candidates, shortlisted, rejected))
    return output


def top_companies(session: Session, *, limit: int = 10) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Experience.company_name, func.count(func.distinct(Experience.candidate_id)))
        .join(Candidate, and_(Candidate.id == Experience.candidate_id, Candidate.is_deleted.is_(False)))
        .group_by(Experience.company_name)
        .order_by(func.count(func.distinct(Experience.candidate_id)).desc())
        .limit(limit)
    ).all()
    return [(name, int(total)) for name, total in rows]


def top_certifications(session: Session, *, limit: int = 10) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Certification.name, func.count(func.distinct(Certification.candidate_id)))
        .join(Candidate, and_(Candidate.id == Certification.candidate_id, Candidate.is_deleted.is_(False)))
        .group_by(Certification.name)
        .order_by(func.count(func.distinct(Certification.candidate_id)).desc())
        .limit(limit)
    ).all()
    return [(name, int(total)) for name, total in rows]


def average_experience(session: Session) -> float:
    value = session.scalar(
        select(func.avg(Candidate.total_experience_years)).where(Candidate.is_deleted.is_(False))
    )
    return round(float(value or 0.0), 2)


def average_match_score(session: Session) -> float | None:
    value = session.scalar(
        select(func.avg(Candidate.last_match_score)).where(
            Candidate.is_deleted.is_(False), Candidate.last_match_score.isnot(None)
        )
    )
    return round(float(value), 2) if value is not None else None


def new_uploads_today(session: Session) -> int:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    return count_resumes(session, since=start)


def resume_processing_stats(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count(Resume.id))) or 0
    completed = count_resumes(session, status=ResumeStatus.COMPLETED.value)
    failed = count_resumes(session, status=ResumeStatus.FAILED.value)
    duplicates = count_resumes(session, status=ResumeStatus.DUPLICATE.value)
    processing = (
        session.scalar(
            select(func.count(Resume.id)).where(
                Resume.status.in_(
                    [
                        ResumeStatus.QUEUED.value,
                        ResumeStatus.PARSING.value,
                        ResumeStatus.EMBEDDING.value,
                        ResumeStatus.GRAPH_SYNC.value,
                    ]
                )
            )
        )
        or 0
    )
    average_ms = session.scalar(select(func.avg(Resume.parse_duration_ms))) or 0
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "duplicates": duplicates,
        "processing": processing,
        "success_rate": round(100 * completed / total, 2) if total else 0.0,
        "average_parse_ms": round(float(average_ms), 1),
    }


def skills_per_candidate(session: Session) -> float:
    candidates = count_candidates(session)
    if not candidates:
        return 0.0
    links = session.scalar(select(func.count(CandidateSkill.id))) or 0
    return round(links / candidates, 2)


def taxonomy_coverage(session: Session) -> float:
    """Share of extracted skills that resolved to the authoritative taxonomy."""
    total = session.scalar(select(func.count(CandidateSkill.id))) or 0
    if not total:
        return 0.0
    matched = session.scalar(select(func.count(CandidateSkill.id)).where(CandidateSkill.skill_id.isnot(None))) or 0
    return round(100 * matched / total, 2)


def recent_uploads(session: Session, *, limit: int = 8) -> list[Resume]:
    return list(
        session.scalars(
            select(Resume)
            .options(selectinload(Resume.candidate), selectinload(Resume.uploaded_by))
            .order_by(Resume.created_at.desc())
            .limit(limit)
        )
    )


def recent_match_runs(session: Session, *, limit: int = 5) -> list[MatchRun]:
    return list(
        session.scalars(
            select(MatchRun)
            .options(selectinload(MatchRun.results), selectinload(MatchRun.created_by))
            .order_by(MatchRun.created_at.desc())
            .limit(limit)
        )
    )


def candidates_added_between(session: Session, start: datetime, end: datetime) -> int:
    return (
        session.scalar(
            select(func.count(Candidate.id)).where(
                Candidate.created_at >= start, Candidate.created_at < end, Candidate.is_deleted.is_(False)
            )
        )
        or 0
    )


def stale_candidates(session: Session, *, days: int = 30, limit: int = 10) -> list[Candidate]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return list(
        session.scalars(
            select(Candidate)
            .where(
                Candidate.is_deleted.is_(False),
                Candidate.updated_at < cutoff,
                Candidate.status.in_([CandidateStatus.NEW.value, CandidateStatus.PENDING_REVIEW.value]),
            )
            .order_by(Candidate.updated_at.asc())
            .limit(limit)
        )
    )
