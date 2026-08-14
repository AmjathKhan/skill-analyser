"""Candidate, resume and recruiter-note schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.constants import CandidateStatus


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int | None = None
    name: str
    category: str | None = None
    technology_stack: str | None = None
    proficiency: str | None = None
    years_experience: float | None = None
    confidence: float = 0.0
    source: str | None = None
    evidence: str | None = None
    mention_count: int = 1
    is_primary: bool = False
    in_taxonomy: bool = True


class ExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    job_title: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    duration_months: int | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)


class EducationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    start_year: int | None = None
    graduation_year: int | None = None
    grade: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class CertificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    issuer: str | None = None
    credential_id: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    url: str | None = None


class RecruiterNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    rating: int | None = None
    is_private: bool = False
    author_id: int | None = None
    author_name: str | None = None
    created_at: datetime


class RecruiterNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    is_private: bool = False


class ResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    original_filename: str
    extension: str
    file_size: int
    status: str
    page_count: int | None = None
    word_count: int | None = None
    ocr_used: bool = False
    extraction_backend: str | None = None
    parse_error: str | None = None
    duplicate_of_id: int | None = None
    parse_duration_ms: int | None = None
    created_at: datetime
    uploaded_by_id: int | None = None
    uploaded_by_name: str | None = None
    candidate_id: int | None = None
    download_url: str | None = None


class ResumeDetail(ResumeSummary):
    raw_text: str | None = None
    parsed_data: dict | None = None


class CandidateListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    full_name: str
    email: EmailStr | str | None = None
    phone: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    city: str | None = None
    country: str | None = None
    total_experience_years: float = 0.0
    highest_degree: str | None = None
    status: str
    availability: str | None = None
    last_match_score: float | None = None
    profile_completeness: float | None = None
    top_skills: list[str] = Field(default_factory=list)
    resume_count: int = 0
    created_at: datetime
    updated_at: datetime


class CandidateDetail(CandidateListItem):
    address: str | None = None
    state: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    headline: str | None = None
    notice_period_days: int | None = None
    expected_ctc: str | None = None
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    ai_highlights: list[str] = Field(default_factory=list)
    graph_synced_at: datetime | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    skills: list[SkillRead] = Field(default_factory=list)
    experiences: list[ExperienceRead] = Field(default_factory=list)
    educations: list[EducationRead] = Field(default_factory=list)
    projects: list[ProjectRead] = Field(default_factory=list)
    certifications: list[CertificationRead] = Field(default_factory=list)
    notes: list[RecruiterNoteRead] = Field(default_factory=list)
    resumes: list[ResumeSummary] = Field(default_factory=list)
    #: Career timeline entries ordered oldest -> newest for the profile page.
    timeline: list[dict] = Field(default_factory=list)


class CandidateUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=512)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    country: str | None = Field(default=None, max_length=128)
    linkedin_url: str | None = Field(default=None, max_length=512)
    github_url: str | None = Field(default=None, max_length=512)
    portfolio_url: str | None = Field(default=None, max_length=512)
    headline: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    current_company_name: str | None = Field(default=None, max_length=255)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
    highest_degree: str | None = Field(default=None, max_length=128)
    status: CandidateStatus | None = None
    availability: str | None = Field(default=None, max_length=64)
    notice_period_days: int | None = Field(default=None, ge=0, le=365)
    expected_ctc: str | None = Field(default=None, max_length=64)
    tags: list[str] | None = None
    owner_id: int | None = None


class CandidateStatusUpdate(BaseModel):
    status: CandidateStatus
    reason: str | None = Field(default=None, max_length=500)


class SimilarCandidate(BaseModel):
    """A peer found through shared skills in the knowledge graph."""

    candidate_id: int
    candidate_uuid: str
    full_name: str
    current_title: str | None = None
    total_experience_years: float = 0.0
    shared_skills: int = 0
    shared_skill_names: list[str] = Field(default_factory=list)
    similarity_percent: float = 0.0


class CandidateFilters(BaseModel):
    """Query filters for the candidate list endpoint."""

    search: str | None = None
    #: ``all`` requires every search term (list page), ``any`` widens it (free text search).
    search_mode: Literal["all", "any"] = "all"
    status: list[str] | None = None
    skills: list[str] | None = None
    min_experience: float | None = Field(default=None, ge=0, le=60)
    max_experience: float | None = Field(default=None, ge=0, le=60)
    location: str | None = None
    company: str | None = None
    education: str | None = None
    certification: str | None = None
    technology: str | None = None
    availability: str | None = None
    owner_id: int | None = None
    uploaded_after: datetime | None = None
    #: Restrict to a pre-computed set (used by search after retrieval).
    candidate_ids: list[int] | None = None
    sort_by: str = "created_at"
    sort_dir: str = "desc"
    page: int = Field(default=1, ge=1)
    #: HTTP endpoints cap this at 100; internal callers (search, exports) fetch larger pools.
    page_size: int = Field(default=20, ge=1, le=2000)


class UploadedResumeResult(BaseModel):
    filename: str
    resume_id: int | None = None
    resume_uuid: str | None = None
    candidate_id: int | None = None
    status: str
    is_duplicate: bool = False
    duplicate_of_resume_id: int | None = None
    task_id: str | None = None
    message: str | None = None
    error: str | None = None
    processing: dict | None = None


class UploadResponse(BaseModel):
    uploaded: int = 0
    failed: int = 0
    duplicates: int = 0
    queued: int = 0
    processed_inline: bool = False
    results: list[UploadedResumeResult] = Field(default_factory=list)
