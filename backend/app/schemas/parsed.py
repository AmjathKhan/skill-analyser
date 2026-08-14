"""Structured output of the resume parsing pipeline (stored on Resume.parsed_data)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ParsedPersonal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    headline: str | None = None


class ParsedExperience(BaseModel):
    company_name: str
    job_title: str | None = None
    employment_type: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    duration_months: int | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    location: str | None = None
    start_year: int | None = None
    graduation_year: int | None = None
    grade: str | None = None
    description: str | None = None


class ParsedProject(BaseModel):
    name: str
    role: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class ParsedCertification(BaseModel):
    name: str
    issuer: str | None = None
    credential_id: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    url: str | None = None


class SkillMention(BaseModel):
    """A raw skill phrase found in the resume, before taxonomy normalization."""

    raw_text: str
    source: str
    evidence: str | None = None
    mention_count: int = 1
    confidence: float = 0.8
    years_experience: float | None = None
    last_used_year: int | None = None


class ParsedResume(BaseModel):
    model_config = ConfigDict(extra="ignore")

    personal: ParsedPersonal = Field(default_factory=ParsedPersonal)
    summary: str | None = None
    total_experience_years: float = 0.0
    current_title: str | None = None
    current_company: str | None = None
    highest_degree: str | None = None
    experiences: list[ParsedExperience] = Field(default_factory=list)
    educations: list[ParsedEducation] = Field(default_factory=list)
    projects: list[ParsedProject] = Field(default_factory=list)
    certifications: list[ParsedCertification] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    skill_mentions: list[SkillMention] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    extraction_backend: str = "rule-based"
