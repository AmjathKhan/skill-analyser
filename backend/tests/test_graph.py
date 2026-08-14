"""Knowledge graph backend and builder tests."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import NodeLabel, RelationType
from app.graph.base import GraphEdge, GraphNode, node_key
from app.graph.builder import candidate_key, skill_key
from app.graph.networkx_backend import NetworkXGraphBackend
from app.graph.registry import get_graph


def build_sample_graph() -> NetworkXGraphBackend:
    graph = NetworkXGraphBackend()
    nodes = [
        GraphNode.create(NodeLabel.CANDIDATE.value, 1, "Priya Sharma"),
        GraphNode.create(NodeLabel.CANDIDATE.value, 2, "Arjun Mehta"),
        GraphNode.create(NodeLabel.SKILL.value, "Python", "Python"),
        GraphNode.create(NodeLabel.SKILL.value, "FastAPI", "FastAPI"),
        GraphNode.create(NodeLabel.SKILL.value, "Apache Spark", "Apache Spark"),
        GraphNode.create(NodeLabel.COMPANY.value, "Zentara", "Zentara Technologies"),
    ]
    graph.upsert_nodes(nodes)
    graph.upsert_edges(
        [
            GraphEdge(nodes[0].key, nodes[2].key, RelationType.HAS_SKILL.value, 1.0),
            GraphEdge(nodes[0].key, nodes[3].key, RelationType.HAS_SKILL.value, 0.9),
            GraphEdge(nodes[1].key, nodes[2].key, RelationType.HAS_SKILL.value, 0.8),
            GraphEdge(nodes[1].key, nodes[4].key, RelationType.HAS_SKILL.value, 1.0),
            GraphEdge(nodes[2].key, nodes[3].key, RelationType.RELATED_TO.value, 0.6),
            GraphEdge(nodes[0].key, nodes[5].key, RelationType.WORKED_AT.value, 1.0),
        ]
    )
    return graph


def test_node_key_is_stable_and_normalized() -> None:
    assert node_key("Skill", "React JS") == node_key("Skill", "react.js") or node_key(
        "Skill", "React JS"
    ).startswith("Skill:")
    assert node_key("Candidate", 7) == "Candidate:7"


def test_upsert_is_idempotent() -> None:
    graph = build_sample_graph()
    before = graph.stats()
    graph.upsert_nodes([GraphNode.create(NodeLabel.SKILL.value, "Python", "Python")])
    after = graph.stats()
    assert after.node_count == before.node_count


def test_neighbours_and_traversal() -> None:
    graph = build_sample_graph()
    start = node_key(NodeLabel.CANDIDATE.value, 1)

    direct = graph.neighbours(start)
    assert {path.node.name for path in direct} == {"Python", "FastAPI", "Zentara Technologies"}

    filtered = graph.neighbours(start, relations=[RelationType.HAS_SKILL.value])
    assert {path.node.name for path in filtered} == {"Python", "FastAPI"}

    # Directed traversal follows Candidate -> Skill -> related Skill.
    forward = graph.traverse(start, depth=2)
    assert {path.node.name for path in forward} >= {"Python", "FastAPI", "Zentara Technologies"}
    assert all(path.depth <= 2 for path in forward)
    assert all(0 < path.weight <= 1 for path in forward)

    # Undirected traversal reaches candidates from a skill.
    deep = graph.traverse(node_key(NodeLabel.SKILL.value, "Apache Spark"), depth=2, undirected=True)
    assert any(path.node.name == "Arjun Mehta" for path in deep)


def test_find_candidates_by_skills() -> None:
    graph = build_sample_graph()
    matches = graph.find_candidates_by_skills(
        [node_key(NodeLabel.SKILL.value, "Python"), node_key(NodeLabel.SKILL.value, "FastAPI")]
    )
    priya = node_key(NodeLabel.CANDIDATE.value, 1)
    arjun = node_key(NodeLabel.CANDIDATE.value, 2)
    assert len(matches[priya]) == 2
    assert len(matches[arjun]) == 1


def test_subgraph_extraction() -> None:
    graph = build_sample_graph()
    nodes, edges = graph.subgraph([node_key(NodeLabel.CANDIDATE.value, 1)], depth=1)
    names = {node.name for node in nodes}
    assert "Priya Sharma" in names
    assert "Python" in names
    assert edges and all(edge.relation for edge in edges)


def test_delete_node_and_edges() -> None:
    graph = build_sample_graph()
    key = node_key(NodeLabel.CANDIDATE.value, 1)
    graph.delete_node(key)
    assert graph.get_node(key) is None
    assert graph.neighbours(key) == []


def test_stats_counts_by_label() -> None:
    graph = build_sample_graph()
    stats = graph.stats()
    assert stats.backend == "networkx"
    assert stats.healthy
    assert stats.node_counts[NodeLabel.SKILL.value] == 3
    assert stats.relationship_counts[RelationType.HAS_SKILL.value] == 4


def test_builder_syncs_taxonomy_and_candidates(client, db_session: Session, uploaded_candidates) -> None:
    """The API lifespan + resume ingestion should leave a populated graph."""
    graph = get_graph()
    stats = graph.stats()
    assert stats.node_count > 50
    assert stats.node_counts.get(NodeLabel.SKILL.value, 0) > 20
    assert stats.node_counts.get(NodeLabel.CANDIDATE.value, 0) >= 3

    candidate_id = next(item["candidate_id"] for item in uploaded_candidates if item.get("candidate_id"))
    node = graph.get_node(candidate_key(candidate_id))
    assert node is not None

    skills = graph.neighbours(candidate_key(candidate_id), relations=[RelationType.HAS_SKILL.value])
    assert skills, "candidate should be connected to skill nodes"
    assert graph.get_node(skill_key("Python")) is not None
