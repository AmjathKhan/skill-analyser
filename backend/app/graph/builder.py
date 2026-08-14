"""Knowledge graph construction from the relational data.

Node labels : Candidate, Skill, Technology, Company, Certification, Project,
              Education, JobRole, Department, Category
Relationships: Candidate-HAS_SKILL->Skill, Skill-BELONGS_TO->Category,
              Skill-RELATED_TO->Skill, Skill-PARENT_OF->Skill,
              Candidate-WORKED_AT->Company, Candidate-COMPLETED->Project,
              Candidate-HOLDS->Certification, Candidate-STUDIED_AT->Education,
              Skill-REQUIRED_FOR->JobRole, Technology-DEPENDS_ON->Technology,
              Company-USES->Technology, Project-USED_SKILL->Skill,
              Skill-PART_OF->Technology, JobRole-PART_OF->Department
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.text_utils import normalize_key
from app.core.constants import NodeLabel as NL
from app.core.constants import RelationType as RT
from app.core.logging import get_logger
from app.graph.base import GraphBackend, GraphEdge, GraphNode, GraphStats, node_key
from app.graph.registry import get_graph, mark_hydrated
from app.models.ai import KnowledgeGraphMetadata
from app.models.candidate import Candidate, CandidateSkill
from app.models.skill import JobRole, Skill, SkillRelation

logger = get_logger(__name__)


@dataclass(slots=True)
class BuildResult:
    nodes: int = 0
    edges: int = 0
    candidates: int = 0
    skills: int = 0
    duration_ms: int = 0
    backend: str = "networkx"
    node_counts: dict[str, int] = field(default_factory=dict)
    relationship_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "candidates": self.candidates,
            "skills": self.skills,
            "duration_ms": self.duration_ms,
            "backend": self.backend,
            "node_counts": self.node_counts,
            "relationship_counts": self.relationship_counts,
        }


def candidate_key(candidate_id: int) -> str:
    return node_key(NL.CANDIDATE.value, candidate_id)


def skill_key(name: str) -> str:
    return node_key(NL.SKILL.value, name)


class KnowledgeGraphBuilder:
    """Projects PostgreSQL rows into the configured graph backend."""

    def __init__(self, session: Session, graph: GraphBackend | None = None) -> None:
        self.session = session
        self.graph = graph or get_graph()

    # ------------------------------------------------------------ taxonomy part
    def sync_taxonomy(self) -> tuple[int, int]:
        skills = list(
            self.session.scalars(
                select(Skill).options(selectinload(Skill.category), selectinload(Skill.job_roles))
            )
        )
        relations = list(self.session.scalars(select(SkillRelation)))
        job_roles = list(self.session.scalars(select(JobRole)))

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        technologies: set[str] = set()
        departments: set[str] = set()
        skill_key_by_id: dict[int, str] = {}

        for skill in skills:
            key = skill_key(skill.name)
            skill_key_by_id[skill.id] = key
            nodes.append(
                GraphNode(
                    label=NL.SKILL.value,
                    key=key,
                    name=skill.name,
                    properties={
                        "skill_id": skill.id,
                        "slug": skill.slug,
                        "category": skill.category.name if skill.category else None,
                        "technology_stack": skill.technology_stack,
                        "experience_level": skill.experience_level,
                        "is_technical": skill.is_technical,
                    },
                )
            )
            if skill.category:
                category_key = node_key(NL.CATEGORY.value, skill.category.name)
                nodes.append(
                    GraphNode(
                        label=NL.CATEGORY.value,
                        key=category_key,
                        name=skill.category.name,
                        properties={"category_id": skill.category.id},
                    )
                )
                edges.append(GraphEdge(key, category_key, RT.BELONGS_TO.value, 1.0))
            if skill.technology_stack:
                technology_key = node_key(NL.TECHNOLOGY.value, skill.technology_stack)
                if skill.technology_stack not in technologies:
                    technologies.add(skill.technology_stack)
                    nodes.append(
                        GraphNode(
                            label=NL.TECHNOLOGY.value,
                            key=technology_key,
                            name=skill.technology_stack,
                            properties={"kind": "stack"},
                        )
                    )
                edges.append(GraphEdge(key, technology_key, RT.PART_OF.value, 0.8))

        for role in job_roles:
            role_key = node_key(NL.JOB_ROLE.value, role.name)
            nodes.append(
                GraphNode(
                    label=NL.JOB_ROLE.value,
                    key=role_key,
                    name=role.name,
                    properties={"job_role_id": role.id, "department": role.department},
                )
            )
            if role.department:
                department_key = node_key(NL.DEPARTMENT.value, role.department)
                if role.department not in departments:
                    departments.add(role.department)
                    nodes.append(
                        GraphNode(label=NL.DEPARTMENT.value, key=department_key, name=role.department)
                    )
                edges.append(GraphEdge(role_key, department_key, RT.PART_OF.value, 1.0))

        for skill in skills:
            key = skill_key_by_id[skill.id]
            if skill.parent_skill_id and skill.parent_skill_id in skill_key_by_id:
                parent_key = skill_key_by_id[skill.parent_skill_id]
                edges.append(GraphEdge(parent_key, key, RT.PARENT_OF.value, 0.75))
                edges.append(GraphEdge(key, parent_key, RT.DEPENDS_ON.value, 0.7))
            for role in skill.job_roles:
                edges.append(GraphEdge(key, node_key(NL.JOB_ROLE.value, role.name), RT.REQUIRED_FOR.value, 0.9))

        for relation in relations:
            source = skill_key_by_id.get(relation.source_skill_id)
            target = skill_key_by_id.get(relation.target_skill_id)
            if not source or not target:
                continue
            edges.append(GraphEdge(source, target, relation.relation_type, relation.weight))
            edges.append(GraphEdge(target, source, relation.relation_type, relation.weight * 0.9))

        # Technology DEPENDS_ON Technology, inferred from cross-stack skill relations.
        stack_by_skill = {skill.id: skill.technology_stack for skill in skills if skill.technology_stack}
        seen_stack_edges: set[tuple[str, str]] = set()
        for relation in relations:
            source_stack = stack_by_skill.get(relation.source_skill_id)
            target_stack = stack_by_skill.get(relation.target_skill_id)
            if not source_stack or not target_stack or source_stack == target_stack:
                continue
            pair = (source_stack, target_stack)
            if pair in seen_stack_edges:
                continue
            seen_stack_edges.add(pair)
            edges.append(
                GraphEdge(
                    node_key(NL.TECHNOLOGY.value, source_stack),
                    node_key(NL.TECHNOLOGY.value, target_stack),
                    RT.DEPENDS_ON.value,
                    0.5,
                )
            )

        written_nodes = self.graph.upsert_nodes(_dedupe_nodes(nodes))
        written_edges = self.graph.upsert_edges(edges)
        logger.info("graph taxonomy synced: %s nodes, %s edges", written_nodes, written_edges)
        return written_nodes, written_edges

    # ----------------------------------------------------------- candidate part
    def sync_candidate(self, candidate: Candidate, *, replace: bool = True) -> tuple[int, int]:
        key = candidate_key(candidate.id)
        if replace:
            self.graph.delete_edges_from(
                key,
                [
                    RT.HAS_SKILL.value,
                    RT.WORKED_AT.value,
                    RT.COMPLETED.value,
                    RT.HOLDS.value,
                    RT.STUDIED_AT.value,
                ],
            )

        nodes: list[GraphNode] = [
            GraphNode(
                label=NL.CANDIDATE.value,
                key=key,
                name=candidate.full_name,
                properties={
                    "candidate_id": candidate.id,
                    "uuid": candidate.uuid,
                    "email": candidate.email,
                    "status": candidate.status,
                    "experience_years": candidate.total_experience_years,
                    "current_title": candidate.current_title,
                    "current_company": candidate.current_company_name,
                    "city": candidate.city,
                    "country": candidate.country,
                    "highest_degree": candidate.highest_degree,
                },
            )
        ]
        edges: list[GraphEdge] = []

        for link in candidate.skills:
            name = link.skill.name if link.skill else link.raw_text
            target = skill_key(name)
            if link.skill is None:
                # Skill outside the taxonomy: keep it as an unverified node.
                nodes.append(
                    GraphNode(
                        label=NL.SKILL.value,
                        key=target,
                        name=name,
                        properties={"in_taxonomy": False},
                    )
                )
            edges.append(
                GraphEdge(
                    key,
                    target,
                    RT.HAS_SKILL.value,
                    round(float(link.confidence or 0.8), 3),
                    {
                        "proficiency": link.proficiency,
                        "years": link.years_experience,
                        "source": link.source,
                    },
                )
            )

        for experience in candidate.experiences:
            company_key = node_key(NL.COMPANY.value, experience.company_name)
            nodes.append(
                GraphNode(
                    label=NL.COMPANY.value,
                    key=company_key,
                    name=experience.company_name,
                    properties={"company_id": experience.company_id},
                )
            )
            edges.append(
                GraphEdge(
                    key,
                    company_key,
                    RT.WORKED_AT.value,
                    1.0,
                    {
                        "title": experience.job_title,
                        "months": experience.duration_months,
                        "is_current": experience.is_current,
                    },
                )
            )
            for technology in experience.technologies or []:
                technology_key = node_key(NL.TECHNOLOGY.value, str(technology))
                nodes.append(
                    GraphNode(
                        label=NL.TECHNOLOGY.value,
                        key=technology_key,
                        name=str(technology),
                        properties={"kind": "tool"},
                    )
                )
                edges.append(GraphEdge(company_key, technology_key, RT.USES.value, 0.6))

        for project in candidate.projects:
            project_key = node_key(NL.PROJECT.value, f"{candidate.id}-{normalize_key(project.name)}")
            nodes.append(
                GraphNode(
                    label=NL.PROJECT.value,
                    key=project_key,
                    name=project.name,
                    properties={"project_id": project.id, "candidate_id": candidate.id, "url": project.url},
                )
            )
            edges.append(GraphEdge(key, project_key, RT.COMPLETED.value, 1.0, {"role": project.role}))
            for technology in project.technologies or []:
                edges.append(GraphEdge(project_key, skill_key(str(technology)), RT.USED_SKILL.value, 0.7))

        for certification in candidate.certifications:
            certification_key = node_key(NL.CERTIFICATION.value, certification.normalized_name or certification.name)
            nodes.append(
                GraphNode(
                    label=NL.CERTIFICATION.value,
                    key=certification_key,
                    name=certification.name,
                    properties={"issuer": certification.issuer},
                )
            )
            edges.append(
                GraphEdge(
                    key,
                    certification_key,
                    RT.HOLDS.value,
                    1.0,
                    {"issued": certification.issue_date.isoformat() if certification.issue_date else None},
                )
            )

        for education in candidate.educations:
            institution = education.institution or education.degree or "Unknown Institution"
            education_key = node_key(NL.EDUCATION.value, institution)
            nodes.append(
                GraphNode(
                    label=NL.EDUCATION.value,
                    key=education_key,
                    name=institution,
                    properties={"degree": education.degree, "field": education.field_of_study},
                )
            )
            edges.append(
                GraphEdge(
                    key,
                    education_key,
                    RT.STUDIED_AT.value,
                    1.0,
                    {"degree": education.degree, "year": education.graduation_year},
                )
            )

        written_nodes = self.graph.upsert_nodes(_dedupe_nodes(nodes))
        written_edges = self.graph.upsert_edges(edges)
        candidate.graph_synced_at = datetime.now(UTC)
        return written_nodes, written_edges

    def remove_candidate(self, candidate_id: int) -> None:
        self.graph.delete_node(candidate_key(candidate_id))

    # ------------------------------------------------------------------- driver
    def build_full(self, *, clear: bool = True, triggered_by_id: int | None = None) -> BuildResult:
        started = time.perf_counter()
        if clear:
            self.graph.clear()

        taxonomy_nodes, taxonomy_edges = self.sync_taxonomy()
        total_nodes, total_edges = taxonomy_nodes, taxonomy_edges

        candidates = list(
            self.session.scalars(
                select(Candidate)
                .where(Candidate.is_deleted.is_(False))
                .options(
                    selectinload(Candidate.skills).selectinload(CandidateSkill.skill),
                    selectinload(Candidate.experiences),
                    selectinload(Candidate.projects),
                    selectinload(Candidate.certifications),
                    selectinload(Candidate.educations),
                )
            )
        )
        for candidate in candidates:
            nodes, edges = self.sync_candidate(candidate, replace=False)
            total_nodes += nodes
            total_edges += edges

        stats = self.graph.stats()
        duration_ms = int((time.perf_counter() - started) * 1000)
        result = BuildResult(
            nodes=stats.node_count or total_nodes,
            edges=stats.edge_count or total_edges,
            candidates=len(candidates),
            skills=stats.node_counts.get(NL.SKILL.value, 0),
            duration_ms=duration_ms,
            backend=self.graph.name,
            node_counts=stats.node_counts,
            relationship_counts=stats.relationship_counts,
        )
        self._record_metadata(result, stats, triggered_by_id)
        mark_hydrated(True)
        logger.info(
            "knowledge graph built: %s nodes / %s edges in %sms (%s)",
            result.nodes,
            result.edges,
            duration_ms,
            self.graph.name,
        )
        return result

    def _record_metadata(self, result: BuildResult, stats: GraphStats, triggered_by_id: int | None) -> None:
        metadata = self.session.scalar(select(KnowledgeGraphMetadata).order_by(KnowledgeGraphMetadata.id.desc()))
        if metadata is None:
            metadata = KnowledgeGraphMetadata(backend=self.graph.name)
            self.session.add(metadata)
        metadata.backend = self.graph.name
        metadata.version = (metadata.version or 0) + 1
        metadata.status = "ready" if stats.healthy else "degraded"
        metadata.node_count = result.nodes
        metadata.edge_count = result.edges
        metadata.node_counts = result.node_counts
        metadata.relationship_counts = result.relationship_counts
        metadata.build_duration_ms = result.duration_ms
        metadata.last_build_at = datetime.now(UTC)
        metadata.triggered_by_id = triggered_by_id
        metadata.notes = stats.detail
        self.session.flush()


def _dedupe_nodes(nodes: Iterable[GraphNode]) -> list[GraphNode]:
    merged: dict[str, GraphNode] = {}
    for node in nodes:
        existing = merged.get(node.key)
        if existing is None:
            merged[node.key] = node
            continue
        for key, value in node.properties.items():
            if value is not None:
                existing.properties.setdefault(key, value)
    return list(merged.values())
