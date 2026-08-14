"""Job requirement CRUD (used by AI Skill Match and JD matching)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, require_permission
from app.core.exceptions import NotFoundError
from app.models.job import JobRequirement
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.skill import JobRequirementCreate, JobRequirementRead

router = APIRouter(prefix="/job-requirements", tags=["Job Requirements"])

ReadPermission = Annotated[User, Depends(require_permission("match:run"))]
WritePermission = Annotated[User, Depends(require_permission("candidate:write"))]


def _to_read(requirement: JobRequirement) -> JobRequirementRead:
    def names(raw: list | None) -> list[str]:
        items: list[str] = []
        for item in raw or []:
            if isinstance(item, dict):
                value = item.get("skill") or item.get("name")
                if value:
                    items.append(str(value))
            elif item:
                items.append(str(item))
        return items

    return JobRequirementRead(
        id=requirement.id,
        uuid=requirement.uuid,
        title=requirement.title,
        department=requirement.department,
        location=requirement.location,
        description=requirement.description,
        min_experience_years=requirement.min_experience_years,
        max_experience_years=requirement.max_experience_years,
        required_skills=names(requirement.required_skills),
        preferred_skills=names(requirement.preferred_skills),
        preferred_certifications=[str(item) for item in (requirement.preferred_certifications or [])],
        preferred_domain=requirement.preferred_domain,
        education_requirement=requirement.education_requirement,
        is_active=requirement.is_active,
        created_by_id=requirement.created_by_id,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


@router.get("", response_model=list[JobRequirementRead])
def list_requirements(
    session: DbSession, _: ReadPermission, active_only: bool = Query(True)
) -> list[JobRequirementRead]:
    statement = select(JobRequirement).order_by(JobRequirement.created_at.desc())
    if active_only:
        statement = statement.where(JobRequirement.is_active.is_(True))
    return [_to_read(requirement) for requirement in session.scalars(statement)]


@router.post("", response_model=JobRequirementRead, status_code=201)
def create_requirement(
    payload: JobRequirementCreate, session: DbSession, actor: WritePermission
) -> JobRequirementRead:
    requirement = JobRequirement(
        title=payload.title,
        department=payload.department,
        location=payload.location,
        description=payload.description,
        min_experience_years=payload.min_experience_years,
        max_experience_years=payload.max_experience_years,
        required_skills=[{"skill": skill, "weight": 1.0, "mandatory": False} for skill in payload.required_skills],
        preferred_skills=[{"skill": skill, "weight": 0.5, "mandatory": False} for skill in payload.preferred_skills],
        preferred_certifications=payload.preferred_certifications,
        preferred_domain=payload.preferred_domain,
        education_requirement=payload.education_requirement,
        is_active=payload.is_active,
        created_by_id=actor.id,
    )
    session.add(requirement)
    session.flush()
    return _to_read(requirement)


@router.get("/{requirement_id}", response_model=JobRequirementRead)
def get_requirement(requirement_id: int, session: DbSession, _: ReadPermission) -> JobRequirementRead:
    requirement = session.get(JobRequirement, requirement_id)
    if requirement is None:
        raise NotFoundError(f"Job requirement {requirement_id} not found")
    return _to_read(requirement)


@router.put("/{requirement_id}", response_model=JobRequirementRead)
def update_requirement(
    requirement_id: int, payload: JobRequirementCreate, session: DbSession, _: WritePermission
) -> JobRequirementRead:
    requirement = session.get(JobRequirement, requirement_id)
    if requirement is None:
        raise NotFoundError(f"Job requirement {requirement_id} not found")

    requirement.title = payload.title
    requirement.department = payload.department
    requirement.location = payload.location
    requirement.description = payload.description
    requirement.min_experience_years = payload.min_experience_years
    requirement.max_experience_years = payload.max_experience_years
    requirement.required_skills = [
        {"skill": skill, "weight": 1.0, "mandatory": False} for skill in payload.required_skills
    ]
    requirement.preferred_skills = [
        {"skill": skill, "weight": 0.5, "mandatory": False} for skill in payload.preferred_skills
    ]
    requirement.preferred_certifications = payload.preferred_certifications
    requirement.preferred_domain = payload.preferred_domain
    requirement.education_requirement = payload.education_requirement
    requirement.is_active = payload.is_active
    return _to_read(requirement)


@router.delete("/{requirement_id}", response_model=MessageResponse)
def delete_requirement(requirement_id: int, session: DbSession, _: WritePermission) -> MessageResponse:
    requirement = session.get(JobRequirement, requirement_id)
    if requirement is None:
        raise NotFoundError(f"Job requirement {requirement_id} not found")
    session.delete(requirement)
    return MessageResponse(message="Job requirement deleted")
