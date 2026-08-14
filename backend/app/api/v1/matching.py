"""AI skill matching endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AiRateLimit, DbSession, require_permission
from app.core.constants import AuditAction
from app.core.exceptions import NotFoundError
from app.models.ai import MatchRun
from app.models.job import JobRequirement
from app.models.user import User
from app.schemas.matching import MatchCriteria, MatchResponse, SkillGapItem
from app.services.audit import record_audit
from app.services.graph_service import ensure_hydrated
from app.services.matching import MatchingEngine, analyze_skill_gaps

router = APIRouter(tags=["AI Skill Matching"])

MatchPermission = Annotated[User, Depends(require_permission("match:run"))]


@router.post("/skill-match", response_model=MatchResponse, dependencies=[AiRateLimit])
def skill_match(criteria: MatchCriteria, session: DbSession, actor: MatchPermission) -> MatchResponse:
    """Rank candidates for a requirement with an explainable score breakdown."""
    if criteria.job_requirement_id:
        requirement = session.get(JobRequirement, criteria.job_requirement_id)
        if requirement is None:
            raise NotFoundError(f"Job requirement {criteria.job_requirement_id} not found")
        criteria = _merge_requirement(criteria, requirement)

    ensure_hydrated(session)
    engine = MatchingEngine(session)
    response = engine.run(criteria, user_id=actor.id)

    record_audit(
        session,
        action=AuditAction.SKILL_MATCH,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="match_run",
        entity_id=response.run_id,
        description=(
            f"Matched {response.returned} of {response.total_candidates_evaluated} candidates for "
            f"{criteria.job_title or ', '.join(criteria.required_skills[:4])}"
        ),
        meta={
            "required_skills": criteria.required_skills,
            "min_experience_years": criteria.min_experience_years,
            "top_score": response.results[0].overall_score if response.results else None,
            "duration_ms": response.duration_ms,
        },
    )
    return response


def _merge_requirement(criteria: MatchCriteria, requirement: JobRequirement) -> MatchCriteria:
    def skill_names(raw: list | None) -> list[str]:
        names: list[str] = []
        for item in raw or []:
            if isinstance(item, dict):
                name = item.get("skill") or item.get("name")
                if name:
                    names.append(str(name))
            elif item:
                names.append(str(item))
        return names

    mandatory = [
        str(item.get("skill"))
        for item in (requirement.required_skills or [])
        if isinstance(item, dict) and item.get("mandatory") and item.get("skill")
    ]
    return criteria.model_copy(
        update={
            "required_skills": criteria.required_skills or skill_names(requirement.required_skills),
            "preferred_skills": criteria.preferred_skills or skill_names(requirement.preferred_skills),
            "mandatory_skills": criteria.mandatory_skills or mandatory,
            "preferred_certifications": criteria.preferred_certifications
            or [str(item) for item in (requirement.preferred_certifications or [])],
            "min_experience_years": criteria.min_experience_years or requirement.min_experience_years,
            "max_experience_years": criteria.max_experience_years or requirement.max_experience_years,
            "preferred_domain": criteria.preferred_domain or requirement.preferred_domain,
            "job_title": criteria.job_title or requirement.title,
            "job_description": criteria.job_description or requirement.description,
            "location": criteria.location or requirement.location,
            "education": criteria.education or requirement.education_requirement,
        }
    )


@router.get("/skill-match/runs", response_model=list[dict])
def list_match_runs(
    session: DbSession, _: MatchPermission, limit: int = Query(20, ge=1, le=100)
) -> list[dict]:
    runs = session.scalars(
        select(MatchRun)
        .options(selectinload(MatchRun.results), selectinload(MatchRun.created_by))
        .order_by(MatchRun.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "uuid": run.uuid,
            "title": run.title,
            "criteria": run.criteria,
            "candidates_evaluated": run.candidates_evaluated,
            "top_score": run.top_score,
            "duration_ms": run.duration_ms,
            "graph_backend": run.graph_backend,
            "embedding_model": run.embedding_model,
            "created_by": run.created_by.full_name if run.created_by else None,
            "created_at": run.created_at.isoformat(),
            "results_count": len(run.results),
        }
        for run in runs
    ]


@router.get("/skill-match/runs/{run_id}", response_model=dict)
def get_match_run(run_id: int, session: DbSession, _: MatchPermission) -> dict:
    run = session.scalar(
        select(MatchRun)
        .options(selectinload(MatchRun.results), selectinload(MatchRun.created_by))
        .where(MatchRun.id == run_id)
    )
    if run is None:
        raise NotFoundError(f"Match run {run_id} not found")
    return {
        "id": run.id,
        "uuid": run.uuid,
        "title": run.title,
        "criteria": run.criteria,
        "weights": run.weights,
        "candidates_evaluated": run.candidates_evaluated,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at.isoformat(),
        "created_by": run.created_by.full_name if run.created_by else None,
        "results": [
            {
                "rank": result.rank,
                "candidate_id": result.candidate_id,
                "candidate_name": result.candidate.full_name,
                "overall_score": result.overall_score,
                "skill_score": result.skill_score,
                "semantic_score": result.semantic_score,
                "experience_score": result.experience_score,
                "certification_score": result.certification_score,
                "project_score": result.project_score,
                "confidence": result.confidence,
                "recommendation": result.recommendation,
                "matched_skills": result.matched_skills,
                "related_skills": result.related_skills,
                "missing_skills": result.missing_skills,
                "score_breakdown": result.score_breakdown,
                "explanation": result.explanation,
                "interview_questions": result.interview_questions,
                "learning_recommendations": result.learning_recommendations,
            }
            for result in run.results
        ],
    }


@router.post("/skill-match/gap-analysis", response_model=list[SkillGapItem])
def skill_gap_analysis(skills: list[str], session: DbSession, _: MatchPermission) -> list[SkillGapItem]:
    """Coverage of each skill across the candidate pool, with bridge suggestions."""
    return analyze_skill_gaps(session, skills)
