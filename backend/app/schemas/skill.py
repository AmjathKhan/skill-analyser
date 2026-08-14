"""Skill taxonomy and job requirement schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SkillCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    skill_count: int = 0


class SkillTaxonomyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None = None
    name: str
    slug: str
    category: str | None = None
    parent_skill: str | None = None
    technology_stack: str | None = None
    experience_level: str | None = None
    description: str | None = None
    is_technical: bool = True
    synonyms: list[str] = Field(default_factory=list)
    related_skills: list[str] = Field(default_factory=list)
    job_roles: list[str] = Field(default_factory=list)
    candidate_count: int = 0


class SkillImportResponse(BaseModel):
    source: str
    rows_read: int = 0
    skills_created: int = 0
    skills_updated: int = 0
    categories_created: int = 0
    synonyms_created: int = 0
    relations_created: int = 0
    job_roles_created: int = 0
    parents_linked: int = 0
    skipped_count: int = 0
    skipped: list[str] = Field(default_factory=list)
    embeddings_created: int = 0


class JobRequirementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    department: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=20000)
    min_experience_years: float = Field(default=0.0, ge=0, le=50)
    max_experience_years: float | None = Field(default=None, ge=0, le=60)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    preferred_certifications: list[str] = Field(default_factory=list)
    preferred_domain: str | None = Field(default=None, max_length=128)
    education_requirement: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class JobRequirementRead(JobRequirementCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
