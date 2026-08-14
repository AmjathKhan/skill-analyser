"""Candidate search request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SearchMode = Literal["hybrid", "semantic", "keyword", "graph", "skill"]


class SearchFilters(BaseModel):
    min_experience: float | None = Field(default=None, ge=0, le=60)
    max_experience: float | None = Field(default=None, ge=0, le=60)
    location: str | None = None
    current_company: str | None = None
    education: str | None = None
    certification: str | None = None
    technology: str | None = None
    availability: str | None = None
    status: list[str] | None = None
    skills: list[str] | None = None


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    mode: SearchMode = "hybrid"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    sort_by: Literal["ai_score", "experience", "upload_date", "name"] = "ai_score"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    #: Ask the Graph RAG engine to answer the query in natural language too.
    include_answer: bool = False


class MatchedSkillHit(BaseModel):
    skill: str
    match_type: str
    score: float = 0.0


class SearchHit(BaseModel):
    candidate_id: int
    candidate_uuid: str
    full_name: str
    email: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    location: str | None = None
    total_experience_years: float = 0.0
    status: str | None = None
    highest_degree: str | None = None
    ai_score: float = 0.0
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    graph_score: float = 0.0
    matched_skills: list[MatchedSkillHit] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    related_skills: list[str] = Field(default_factory=list)
    snippet: str | None = None
    channels: list[str] = Field(default_factory=list)
    top_skills: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    mode: str
    interpreted_skills: list[str] = Field(default_factory=list)
    interpreted_experience: float | None = None
    unknown_terms: list[str] = Field(default_factory=list)
    expanded_skills: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    duration_ms: int = 0
    items: list[SearchHit] = Field(default_factory=list)
    answer: str | None = None
    answer_backend: str | None = None
    graph_paths: list[str] = Field(default_factory=list)
    generated_at: datetime


class SuggestResponse(BaseModel):
    skills: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    candidates: list[dict] = Field(default_factory=list)
