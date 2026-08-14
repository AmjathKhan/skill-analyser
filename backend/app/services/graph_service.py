"""Knowledge graph operations exposed through the API."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, NodeLabel
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.graph.base import GraphEdge, GraphNode
from app.graph.builder import KnowledgeGraphBuilder, candidate_key, skill_key
from app.graph.registry import get_graph, mark_hydrated, requires_hydration
from app.models.ai import KnowledgeGraphMetadata
from app.models.candidate import Candidate, CandidateSkill
from app.schemas.graph import (
    GraphBuildRequest,
    GraphBuildResponse,
    GraphEdgeRead,
    GraphNodeRead,
    GraphStatsResponse,
    GraphView,
    SkillGraphNode,
    SkillGraphResponse,
)
from app.services.audit import record_audit
from app.services.taxonomy import get_taxonomy

logger = get_logger(__name__)

LABEL_GROUPS = {
    NodeLabel.CANDIDATE.value: "candidate",
    NodeLabel.SKILL.value: "skill",
    NodeLabel.TECHNOLOGY.value: "technology",
    NodeLabel.COMPANY.value: "company",
    NodeLabel.CERTIFICATION.value: "certification",
    NodeLabel.PROJECT.value: "project",
    NodeLabel.EDUCATION.value: "education",
    NodeLabel.JOB_ROLE.value: "job_role",
    NodeLabel.DEPARTMENT.value: "department",
    NodeLabel.CATEGORY.value: "category",
}


def _to_node_read(node: GraphNode) -> GraphNodeRead:
    return GraphNodeRead(
        id=node.key,
        label=node.label,
        name=node.name,
        properties={key: value for key, value in node.properties.items() if value is not None},
        group=LABEL_GROUPS.get(node.label, "other"),
    )


def _to_edge_read(edge: GraphEdge) -> GraphEdgeRead:
    return GraphEdgeRead(
        source=edge.source_key,
        target=edge.target_key,
        relation=edge.relation,
        weight=edge.weight,
        properties=edge.properties,
    )


def build_graph(session: Session, request: GraphBuildRequest, *, user_id: int | None = None) -> GraphBuildResponse:
    builder = KnowledgeGraphBuilder(session)

    if request.candidate_ids:
        if request.include_taxonomy:
            builder.sync_taxonomy()
        nodes = edges = 0
        from app.repositories.candidate_repository import candidates_by_ids

        candidates = candidates_by_ids(session, request.candidate_ids)
        for candidate in candidates:
            node_count, edge_count = builder.sync_candidate(candidate)
            nodes += node_count
            edges += edge_count
        stats = builder.graph.stats()
        response = GraphBuildResponse(
            backend=builder.graph.name,
            nodes=nodes,
            edges=edges,
            candidates=len(candidates),
            skills=stats.node_counts.get(NodeLabel.SKILL.value, 0),
            duration_ms=0,
            node_counts=stats.node_counts,
            relationship_counts=stats.relationship_counts,
            built_at=datetime.now(UTC),
        )
    else:
        result = builder.build_full(clear=request.clear, triggered_by_id=user_id)
        response = GraphBuildResponse(
            backend=result.backend,
            nodes=result.nodes,
            edges=result.edges,
            candidates=result.candidates,
            skills=result.skills,
            duration_ms=result.duration_ms,
            node_counts=result.node_counts,
            relationship_counts=result.relationship_counts,
            built_at=datetime.now(UTC),
        )

    mark_hydrated(True)
    record_audit(
        session,
        action=AuditAction.GRAPH_BUILD,
        user_id=user_id,
        entity_type="knowledge_graph",
        description=f"Built knowledge graph ({response.nodes} nodes / {response.edges} edges)",
        meta=response.model_dump(mode="json"),
    )
    return response


def ensure_hydrated(session: Session) -> None:
    """The in-memory graph is empty after a restart - rebuild it lazily."""
    if not requires_hydration():
        return
    logger.info("hydrating in-process knowledge graph from PostgreSQL")
    KnowledgeGraphBuilder(session).build_full(clear=True)


def candidate_view(session: Session, candidate_id: int, *, depth: int = 2, limit: int = 250) -> GraphView:
    ensure_hydrated(session)
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or candidate.is_deleted:
        raise NotFoundError(f"Candidate {candidate_id} not found")

    graph = get_graph()
    key = candidate_key(candidate_id)
    nodes, edges = graph.subgraph([key], depth=depth, limit=limit)
    if not nodes:
        KnowledgeGraphBuilder(session, graph).sync_candidate(candidate)
        nodes, edges = graph.subgraph([key], depth=depth, limit=limit)

    return GraphView(
        nodes=[_to_node_read(node) for node in nodes],
        edges=[_to_edge_read(edge) for edge in edges],
        focus=key,
        depth=depth,
        truncated=len(nodes) >= limit,
        backend=graph.name,
    )


def skill_view(session: Session, skill_name: str, *, depth: int = 2, limit: int = 200) -> GraphView:
    ensure_hydrated(session)
    graph = get_graph()
    taxonomy = get_taxonomy(session)
    match = taxonomy.resolve(skill_name)
    canonical = match.skill.name if match else skill_name
    key = skill_key(canonical)
    nodes, edges = graph.subgraph([key], depth=depth, limit=limit)
    return GraphView(
        nodes=[_to_node_read(node) for node in nodes],
        edges=[_to_edge_read(edge) for edge in edges],
        focus=key,
        depth=depth,
        truncated=len(nodes) >= limit,
        backend=graph.name,
    )


def overview_view(session: Session, *, limit: int = 220, candidate_limit: int = 25) -> GraphView:
    """A representative slice of the whole graph for the visualization page."""
    ensure_hydrated(session)
    graph = get_graph()

    candidate_ids = list(
        session.scalars(
            select(Candidate.id)
            .where(Candidate.is_deleted.is_(False))
            .order_by(Candidate.updated_at.desc())
            .limit(candidate_limit)
        )
    )
    keys = [candidate_key(candidate_id) for candidate_id in candidate_ids]

    top_skills = session.execute(
        select(CandidateSkill.normalized_name, func.count(CandidateSkill.id))
        .group_by(CandidateSkill.normalized_name)
        .order_by(func.count(CandidateSkill.id).desc())
        .limit(20)
    ).all()
    taxonomy = get_taxonomy(session)
    for normalized, _ in top_skills:
        node = next((item for item in taxonomy.all_skills() if item.normalized == normalized), None)
        if node:
            keys.append(skill_key(node.name))

    nodes, edges = graph.subgraph(keys, depth=1, limit=limit)
    return GraphView(
        nodes=[_to_node_read(node) for node in nodes],
        edges=[_to_edge_read(edge) for edge in edges],
        focus=None,
        depth=1,
        truncated=len(nodes) >= limit,
        backend=graph.name,
    )


def graph_stats(session: Session) -> GraphStatsResponse:
    graph = get_graph()
    stats = graph.stats()
    metadata = session.scalar(select(KnowledgeGraphMetadata).order_by(KnowledgeGraphMetadata.id.desc()))
    return GraphStatsResponse(
        backend=stats.backend,
        healthy=stats.healthy,
        node_count=stats.node_count,
        edge_count=stats.edge_count,
        node_counts=stats.node_counts,
        relationship_counts=stats.relationship_counts,
        last_build_at=metadata.last_build_at if metadata else None,
        version=metadata.version if metadata else None,
        detail=stats.detail,
    )


def skills_graph(session: Session, *, limit: int = 200, include_view: bool = False) -> SkillGraphResponse:
    taxonomy = get_taxonomy(session)
    counts: dict[int, int] = {
        int(skill_id): int(total)
        for skill_id, total in session.execute(
            select(CandidateSkill.skill_id, func.count(func.distinct(CandidateSkill.candidate_id)))
            .where(CandidateSkill.skill_id.isnot(None))
            .group_by(CandidateSkill.skill_id)
        ).all()
        if skill_id is not None
    }

    skills: list[SkillGraphNode] = []
    for node in taxonomy.all_skills()[:limit]:
        parent = taxonomy.get(node.parent_id) if node.parent_id else None
        skills.append(
            SkillGraphNode(
                skill=node.name,
                category=node.category,
                technology_stack=node.technology_stack,
                parent=parent.name if parent else None,
                children=[child.name for child in (taxonomy.get(child_id) for child_id in node.child_ids) if child],
                related=[
                    related.name
                    for related in (taxonomy.get(related_id) for related_id in node.related_ids)
                    if related
                ][:10],
                job_roles=list(node.job_roles)[:8],
                candidate_count=int(counts.get(node.id, 0)),
            )
        )
    skills.sort(key=lambda item: (-item.candidate_count, item.skill))

    categories = {name: len(nodes) for name, nodes in taxonomy.categories().items()}
    view = None
    if include_view and skills:
        view = skill_view(session, skills[0].skill, depth=2, limit=150)
    return SkillGraphResponse(
        total_skills=taxonomy.size,
        categories=dict(sorted(categories.items(), key=lambda item: -item[1])),
        skills=skills,
        view=view,
    )
