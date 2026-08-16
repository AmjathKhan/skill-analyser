"""Dashboard and reporting schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DashboardCards(BaseModel):
    total_candidates: int = 0
    uploaded_resumes: int = 0
    shortlisted: int = 0
    rejected: int = 0
    pending_review: int = 0
    new_uploads_today: int = 0
    processing: int = 0
    failed_resumes: int = 0
    average_experience_years: float = 0.0
    average_match_score: float | None = None


class NamedValue(BaseModel):
    name: str
    value: float = 0.0
    extra: str | None = None


class TrendPoint(BaseModel):
    period: str
    uploads: int = 0
    candidates: int = 0
    shortlisted: int = 0
    rejected: int = 0


class ActivityItem(BaseModel):
    id: int
    action: str
    actor: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    created_at: datetime
    status: str = "success"


class DashboardResponse(BaseModel):
    cards: DashboardCards
    top_skills: list[NamedValue] = Field(default_factory=list)
    technology_distribution: list[NamedValue] = Field(default_factory=list)
    experience_distribution: list[NamedValue] = Field(default_factory=list)
    candidate_status: list[NamedValue] = Field(default_factory=list)
    hiring_trends: list[TrendPoint] = Field(default_factory=list)
    top_companies: list[NamedValue] = Field(default_factory=list)
    top_certifications: list[NamedValue] = Field(default_factory=list)
    recent_activity: list[ActivityItem] = Field(default_factory=list)
    recent_uploads: list[dict] = Field(default_factory=list)
    ai_recommendations: list[dict] = Field(default_factory=list)
    graph: dict = Field(default_factory=dict)
    generated_at: datetime


class PipelineStage(BaseModel):
    status: str
    label: str
    count: int = 0
    percent: float = 0.0


class RecruitmentKPIs(BaseModel):
    total_candidates: int = 0
    resumes_processed: int = 0
    parse_success_rate: float = 0.0
    average_parse_ms: float = 0.0
    shortlist_rate: float = 0.0
    rejection_rate: float = 0.0
    hired: int = 0
    interviewing: int = 0
    pending_review: int = 0
    failed_resumes: int = 0
    average_experience_years: float = 0.0
    skills_per_candidate: float = 0.0
    taxonomy_coverage_percent: float = 0.0
    unique_skills: int = 0
    unique_companies: int = 0
    new_candidates_in_period: int = 0
    matches_run: int = 0
    average_match_score: float | None = None


class ReportInsight(BaseModel):
    level: str = "info"
    title: str
    detail: str


class ReportResponse(BaseModel):
    generated_at: datetime
    period_start: date | None = None
    period_end: date | None = None
    kpis: RecruitmentKPIs
    insights: list[ReportInsight] = Field(default_factory=list)
    top_technologies: list[NamedValue] = Field(default_factory=list)
    top_skills: list[NamedValue] = Field(default_factory=list)
    top_categories: list[NamedValue] = Field(default_factory=list)
    hiring_trends: list[TrendPoint] = Field(default_factory=list)
    skill_gaps: list[dict] = Field(default_factory=list)
    pipeline: list[PipelineStage] = Field(default_factory=list)
    experience_distribution: list[NamedValue] = Field(default_factory=list)
    top_companies: list[NamedValue] = Field(default_factory=list)
    top_certifications: list[NamedValue] = Field(default_factory=list)
    top_locations: list[NamedValue] = Field(default_factory=list)
    education_distribution: list[NamedValue] = Field(default_factory=list)
    recent_matches: list[dict] = Field(default_factory=list)
