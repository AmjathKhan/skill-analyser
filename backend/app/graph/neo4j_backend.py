"""Neo4j implementation of the knowledge graph backend.

Nodes carry a generic ``:Entity`` label plus their specific label (Candidate,
Skill, Technology, ...) so a single unique constraint on ``Entity.key`` keeps
MERGE operations cheap.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.base import GraphBackend, GraphEdge, GraphNode, GraphPath, GraphStats

logger = get_logger(__name__)

ALLOWED_RELATIONS = {
    "HAS_SKILL", "BELONGS_TO", "RELATED_TO", "PARENT_OF", "WORKED_AT", "COMPLETED",
    "HOLDS", "STUDIED_AT", "REQUIRED_FOR", "DEPENDS_ON", "USES", "PART_OF", "USED_SKILL",
}


class Neo4jGraphBackend(GraphBackend):
    name = "neo4j"

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        from neo4j import GraphDatabase

        self._uri = uri or settings.neo4j_uri
        self._database = database or settings.neo4j_database
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(user or settings.neo4j_user, password or settings.neo4j_password),
            max_connection_lifetime=3600,
        )
        self._driver.verify_connectivity()
        self._ensure_schema()
        logger.info("connected to Neo4j at %s", self._uri)

    # ------------------------------------------------------------------ schema
    def _ensure_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE",
            "CREATE INDEX entity_label IF NOT EXISTS FOR (n:Entity) ON (n.label)",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        ]
        with self._driver.session(database=self._database) as session:
            for statement in statements:
                try:
                    session.run(statement)
                except Exception as exc:
                    logger.debug("neo4j schema statement skipped: %s", exc)

    def close(self) -> None:
        self._driver.close()

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    # ------------------------------------------------------------------ writes
    def upsert_nodes(self, nodes: list[GraphNode]) -> int:
        if not nodes:
            return 0
        by_label: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            by_label.setdefault(node.label, []).append(
                {
                    "key": node.key,
                    "name": node.name,
                    "label": node.label,
                    "props": {k: v for k, v in node.properties.items() if v is not None},
                }
            )
        written = 0
        for label, batch in by_label.items():
            safe_label = _safe_label(label)
            self._run(
                f"""
                UNWIND $rows AS row
                MERGE (n:Entity {{key: row.key}})
                SET n:{safe_label},
                    n.name = row.name,
                    n.label = row.label,
                    n += row.props,
                    n.updated_at = timestamp()
                """,
                rows=batch,
            )
            written += len(batch)
        return written

    def upsert_edges(self, edges: list[GraphEdge]) -> int:
        if not edges:
            return 0
        by_relation: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            relation = edge.relation if edge.relation in ALLOWED_RELATIONS else "RELATED_TO"
            by_relation.setdefault(relation, []).append(
                {
                    "source": edge.source_key,
                    "target": edge.target_key,
                    "weight": edge.weight,
                    "props": {k: v for k, v in edge.properties.items() if v is not None},
                }
            )
        written = 0
        for relation, batch in by_relation.items():
            self._run(
                f"""
                UNWIND $rows AS row
                MATCH (source:Entity {{key: row.source}})
                MATCH (target:Entity {{key: row.target}})
                MERGE (source)-[r:{relation}]->(target)
                SET r.weight = row.weight, r += row.props
                """,
                rows=batch,
            )
            written += len(batch)
        return written

    def delete_node(self, key: str) -> None:
        self._run("MATCH (n:Entity {key: $key}) DETACH DELETE n", key=key)

    def delete_edges_from(self, key: str, relations: list[str] | None = None) -> None:
        if relations:
            relation_pattern = "|".join(_safe_relation(relation) for relation in relations)
            self._run(f"MATCH (n:Entity {{key: $key}})-[r:{relation_pattern}]->() DELETE r", key=key)
        else:
            self._run("MATCH (n:Entity {key: $key})-[r]->() DELETE r", key=key)

    def clear(self) -> None:
        self._run("MATCH (n:Entity) DETACH DELETE n")

    # ------------------------------------------------------------------- reads
    def get_node(self, key: str) -> GraphNode | None:
        rows = self._run("MATCH (n:Entity {key: $key}) RETURN n LIMIT 1", key=key)
        if not rows:
            return None
        return _to_node(rows[0]["n"])

    def traverse(
        self,
        start_key: str,
        *,
        depth: int = 2,
        relations: list[str] | None = None,
        labels: list[str] | None = None,
        limit: int = 200,
        undirected: bool = False,
    ) -> list[GraphPath]:
        relation_pattern = ""
        if relations:
            relation_pattern = ":" + "|".join(_safe_relation(relation) for relation in relations)
        depth = max(1, min(depth, 4))
        arrow = "" if undirected else ">"
        rows = self._run(
            f"""
            MATCH path = (start:Entity {{key: $key}})-[{relation_pattern}*1..{depth}]-{arrow}(node:Entity)
            WHERE ($labels IS NULL OR node.label IN $labels) AND node.key <> $key
            WITH node, path,
                 reduce(w = 1.0, rel IN relationships(path) | w * coalesce(rel.weight, 1.0)) AS weight,
                 [n IN nodes(path)[0..-1] | n.name] AS via,
                 last(relationships(path)) AS lastRel
            RETURN node, weight, via, type(lastRel) AS relation, length(path) AS depth
            ORDER BY weight DESC, depth ASC
            LIMIT $limit
            """,
            key=start_key,
            labels=labels,
            limit=limit,
        )
        seen: set[str] = set()
        paths: list[GraphPath] = []
        for row in rows:
            node = _to_node(row["node"])
            if node.key in seen:
                continue
            seen.add(node.key)
            paths.append(
                GraphPath(
                    node=node,
                    relation=row.get("relation") or "RELATED_TO",
                    depth=int(row.get("depth") or 1),
                    weight=float(row.get("weight") or 1.0),
                    via=[value for value in (row.get("via") or []) if value],
                )
            )
        return paths

    def neighbours(
        self, key: str, *, relations: list[str] | None = None, labels: list[str] | None = None, limit: int = 200
    ) -> list[GraphPath]:
        relation_pattern = ""
        if relations:
            relation_pattern = ":" + "|".join(_safe_relation(relation) for relation in relations)
        rows = self._run(
            f"""
            MATCH (start:Entity {{key: $key}})-[r{relation_pattern}]-(node:Entity)
            WHERE $labels IS NULL OR node.label IN $labels
            RETURN node, type(r) AS relation, coalesce(r.weight, 1.0) AS weight, start.name AS via
            ORDER BY weight DESC
            LIMIT $limit
            """,
            key=key,
            labels=labels,
            limit=limit,
        )
        return [
            GraphPath(
                node=_to_node(row["node"]),
                relation=row["relation"],
                depth=1,
                weight=float(row["weight"] or 1.0),
                via=[row["via"]] if row.get("via") else [],
            )
            for row in rows
        ]

    def subgraph(self, keys: list[str], *, depth: int = 1, limit: int = 400) -> tuple[list[GraphNode], list[GraphEdge]]:
        depth = max(1, min(depth, 3))
        rows = self._run(
            f"""
            MATCH (start:Entity) WHERE start.key IN $keys
            OPTIONAL MATCH path = (start)-[*1..{depth}]-(other:Entity)
            WITH collect(DISTINCT start) + collect(DISTINCT other) AS nodes
            UNWIND nodes AS node
            WITH collect(DISTINCT node) AS nodes
            UNWIND nodes AS a
            OPTIONAL MATCH (a)-[r]->(b:Entity) WHERE b IN nodes
            RETURN collect(DISTINCT a) AS nodes,
                   collect(DISTINCT {{source: startNode(r).key, target: endNode(r).key,
                                      relation: type(r), weight: coalesce(r.weight, 1.0)}}) AS edges
            LIMIT 1
            """,
            keys=keys,
        )
        if not rows:
            return [], []
        raw_nodes = [node for node in (rows[0].get("nodes") or []) if node][:limit]
        nodes = [_to_node(node) for node in raw_nodes]
        node_keys = {node.key for node in nodes}
        edges = [
            GraphEdge(
                source_key=edge["source"],
                target_key=edge["target"],
                relation=edge["relation"],
                weight=float(edge.get("weight") or 1.0),
            )
            for edge in (rows[0].get("edges") or [])
            if edge and edge.get("source") in node_keys and edge.get("target") in node_keys
        ]
        return nodes, edges

    def find_candidates_by_skills(self, skill_keys: list[str], *, limit: int = 500) -> dict[str, list[str]]:
        rows = self._run(
            """
            MATCH (candidate:Candidate)-[:HAS_SKILL]->(skill:Skill)
            WHERE skill.key IN $skill_keys
            RETURN candidate.key AS candidate, collect(DISTINCT skill.key) AS skills
            ORDER BY size(skills) DESC
            LIMIT $limit
            """,
            skill_keys=skill_keys,
            limit=limit,
        )
        return {row["candidate"]: row["skills"] for row in rows}

    def stats(self) -> GraphStats:
        try:
            node_rows = self._run(
                "MATCH (n:Entity) RETURN coalesce(n.label, 'Unknown') AS label, count(*) AS total"
            )
            edge_rows = self._run("MATCH ()-[r]->() RETURN type(r) AS relation, count(*) AS total")
        except Exception as exc:
            return GraphStats(self.name, 0, 0, healthy=False, detail=str(exc))
        node_counts = {row["label"]: int(row["total"]) for row in node_rows}
        relationship_counts = {row["relation"]: int(row["total"]) for row in edge_rows}
        return GraphStats(
            backend=self.name,
            node_count=sum(node_counts.values()),
            edge_count=sum(relationship_counts.values()),
            node_counts=node_counts,
            relationship_counts=relationship_counts,
            healthy=True,
            detail=self._uri,
        )

    def run_cypher(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Escape hatch for analytics queries (read-only usage expected)."""
        return self._run(query, **params)


def _safe_label(label: str) -> str:
    cleaned = "".join(char for char in label if char.isalnum() or char == "_")
    return cleaned or "Entity"


def _safe_relation(relation: str) -> str:
    cleaned = "".join(char for char in relation.upper() if char.isalnum() or char == "_")
    return cleaned if cleaned in ALLOWED_RELATIONS else "RELATED_TO"


def _to_node(raw: dict[str, Any]) -> GraphNode:
    properties = {key: value for key, value in raw.items() if key not in {"key", "name", "label"}}
    return GraphNode(
        label=raw.get("label") or "Unknown",
        key=raw.get("key") or "",
        name=raw.get("name") or raw.get("key", ""),
        properties=properties,
    )
