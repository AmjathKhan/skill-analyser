"""Knowledge graph API schemas (used by the visualization page)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GraphNodeRead(BaseModel):
    id: str
    label: str
    name: str
    properties: dict = Field(default_factory=dict)
    #: Convenience field for the frontend force-graph renderer.
    group: str | None = None


class GraphEdgeRead(BaseModel):
    source: str
    target: str
    relation: str
    weight: float = 1.0
    properties: dict = Field(default_factory=dict)


class GraphView(BaseModel):
    nodes: list[GraphNodeRead] = Field(default_factory=list)
    edges: list[GraphEdgeRead] = Field(default_factory=list)
    focus: str | None = None
    depth: int = 1
    truncated: bool = False
    backend: str = "networkx"


class GraphBuildRequest(BaseModel):
    clear: bool = True
    include_taxonomy: bool = True
    candidate_ids: list[int] | None = None


class GraphBuildResponse(BaseModel):
    backend: str
    nodes: int = 0
    edges: int = 0
    candidates: int = 0
    skills: int = 0
    duration_ms: int = 0
    node_counts: dict[str, int] = Field(default_factory=dict)
    relationship_counts: dict[str, int] = Field(default_factory=dict)
    built_at: datetime


class GraphStatsResponse(BaseModel):
    backend: str
    healthy: bool = True
    node_count: int = 0
    edge_count: int = 0
    node_counts: dict[str, int] = Field(default_factory=dict)
    relationship_counts: dict[str, int] = Field(default_factory=dict)
    last_build_at: datetime | None = None
    version: int | None = None
    detail: str | None = None


class SkillGraphNode(BaseModel):
    skill: str
    category: str | None = None
    technology_stack: str | None = None
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    job_roles: list[str] = Field(default_factory=list)
    candidate_count: int = 0


class SkillGraphResponse(BaseModel):
    total_skills: int = 0
    categories: dict[str, int] = Field(default_factory=dict)
    skills: list[SkillGraphNode] = Field(default_factory=list)
    view: GraphView | None = None
