"""Schemas for the AI skill matching engine and Graph RAG responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import Recommendation


class MatchCriteria(BaseModel):
    """Recruiter input for a skill match run."""

    model_config = ConfigDict(populate_by_name=True)

    required_skills: list[str] = Field(default_factory=list, max_length=60)
    mandatory_skills: list[str] = Field(default_factory=list, max_length=30)
    preferred_skills: list[str] = Field(default_factory=list, max_length=60)
    preferred_certifications: list[str] = Field(default_factory=list, max_length=30)
    min_experience_years: float = Field(default=0.0, ge=0, le=50)
    max_experience_years: float | None = Field(default=None, ge=0, le=60)
    preferred_domain: str | None = Field(default=None, max_length=128)
    job_title: str | None = Field(default=None, max_length=200)
    job_description: str | None = Field(default=None, max_length=20000)
    location: str | None = Field(default=None, max_length=200)
    education: str | None = Field(default=None, max_length=200)
    job_requirement_id: int | None = None
    candidate_ids: list[int] | None = None
    statuses: list[str] | None = None
    top_k: int = Field(default=20, ge=1, le=200)
    min_score: float = Field(default=0.0, ge=0, le=100)
    include_explanations: bool = True
    weights: dict[str, float] | None = None
    persist: bool = True

    @field_validator("required_skills", "preferred_skills", "mandatory_skills", "preferred_certifications")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = (value or "").strip()
            if item and item.lower() not in {existing.lower() for existing in cleaned}:
                cleaned.append(item)
        return cleaned

    @property
    def all_skills(self) -> list[str]:
        return list(dict.fromkeys([*self.required_skills, *self.preferred_skills]))


class SkillEvidence(BaseModel):
    """Why a required skill counted as matched (or why it didn't)."""

    requested: str
    matched_skill: str | None = None
    #: exact | synonym | fuzzy | related | child | parent | semantic | graph | missing
    match_type: str = "missing"
    score: float = 0.0
    confidence: float = 0.0
    proficiency: str | None = None
    years_experience: float | None = None
    source: str | None = None
    evidence: str | None = None
    mandatory: bool = False
    #: Graph path that justified an indirect match, e.g. ["Flask", "RELATED_TO", "Python"].
    graph_path: list[str] = Field(default_factory=list)


class ScoreComponent(BaseModel):
    name: str
    score: float
    weight: float
    contribution: float
    detail: str | None = None


class MatchBreakdown(BaseModel):
    skill_score: float = 0.0
    semantic_score: float = 0.0
    experience_score: float = 0.0
    certification_score: float = 0.0
    project_score: float = 0.0
    components: list[ScoreComponent] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class GraphContextSummary(BaseModel):
    """Compact view of the graph neighbourhood used during retrieval."""

    connected_skills: list[str] = Field(default_factory=list)
    related_technologies: list[str] = Field(default_factory=list)
    equivalent_skills: list[dict[str, str]] = Field(default_factory=list)
    skill_hierarchy: list[dict[str, str]] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    job_roles: list[str] = Field(default_factory=list)
    similar_candidates: list[dict[str, object]] = Field(default_factory=list)
    retrieval_paths: list[str] = Field(default_factory=list)


class CandidateMatch(BaseModel):
    candidate_id: int
    candidate_uuid: str
    full_name: str
    email: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    location: str | None = None
    total_experience_years: float = 0.0
    highest_degree: str | None = None
    status: str | None = None
    rank: int = 0

    overall_score: float = 0.0
    confidence: float = 0.0
    recommendation: str = Recommendation.NOT_RECOMMENDED.value
    breakdown: MatchBreakdown = Field(default_factory=MatchBreakdown)

    matched_skills: list[SkillEvidence] = Field(default_factory=list)
    related_skills: list[SkillEvidence] = Field(default_factory=list)
    missing_skills: list[SkillEvidence] = Field(default_factory=list)
    additional_skills: list[str] = Field(default_factory=list)

    explanation: str | None = None
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    interview_questions: list[str] = Field(default_factory=list)
    learning_recommendations: list[str] = Field(default_factory=list)
    career_fit: str | None = None
    graph_context: GraphContextSummary = Field(default_factory=GraphContextSummary)


class MatchResponse(BaseModel):
    run_id: int | None = None
    run_uuid: str | None = None
    criteria: MatchCriteria
    total_candidates_evaluated: int = 0
    returned: int = 0
    duration_ms: int = 0
    generated_at: datetime
    embedding_model: str | None = None
    graph_backend: str | None = None
    vector_backend: str | None = None
    llm_backend: str | None = None
    results: list[CandidateMatch] = Field(default_factory=list)


class SkillGapItem(BaseModel):
    skill: str
    category: str | None = None
    candidates_with_skill: int = 0
    coverage_percent: float = 0.0
    demand_score: float = 0.0
    suggested_learning: list[str] = Field(default_factory=list)


class GraphRAGAnswer(BaseModel):
    """LLM answer grounded in retrieved graph + vector context."""

    question: str
    answer: str
    candidates_considered: list[dict[str, object]] = Field(default_factory=list)
    context_used: list[str] = Field(default_factory=list)
    graph_paths: list[str] = Field(default_factory=list)
    llm_backend: str = "template"
    generated_at: datetime
