"""In-process knowledge graph backed by ``networkx.MultiDiGraph``.

Used for prototyping/CI and as the automatic fallback when Neo4j is not
reachable. Traversals are breadth-first with weight decay, mirroring the Cypher
variable-length patterns used by the Neo4j backend.
"""

from __future__ import annotations

import threading
from collections import Counter, deque

import networkx as nx

from app.core.logging import get_logger
from app.graph.base import GraphBackend, GraphEdge, GraphNode, GraphPath, GraphStats

logger = get_logger(__name__)


class NetworkXGraphBackend(GraphBackend):
    name = "networkx"

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ writes
    def upsert_nodes(self, nodes: list[GraphNode]) -> int:
        with self._lock:
            for node in nodes:
                self._graph.add_node(
                    node.key,
                    label=node.label,
                    name=node.name,
                    **{key: value for key, value in node.properties.items() if value is not None},
                )
            return len(nodes)

    def upsert_edges(self, edges: list[GraphEdge]) -> int:
        with self._lock:
            written = 0
            for edge in edges:
                if edge.source_key not in self._graph or edge.target_key not in self._graph:
                    continue
                self._graph.add_edge(
                    edge.source_key,
                    edge.target_key,
                    key=edge.relation,
                    relation=edge.relation,
                    weight=edge.weight,
                    **edge.properties,
                )
                written += 1
            return written

    def delete_node(self, key: str) -> None:
        with self._lock:
            if key in self._graph:
                self._graph.remove_node(key)

    def delete_edges_from(self, key: str, relations: list[str] | None = None) -> None:
        with self._lock:
            if key not in self._graph:
                return
            to_remove = [
                (source, target, edge_key)
                for source, target, edge_key, data in self._graph.out_edges(key, keys=True, data=True)
                if relations is None or data.get("relation") in relations
            ]
            for source, target, edge_key in to_remove:
                self._graph.remove_edge(source, target, key=edge_key)

    def clear(self) -> None:
        with self._lock:
            self._graph.clear()

    # ------------------------------------------------------------------- reads
    def get_node(self, key: str) -> GraphNode | None:
        with self._lock:
            if key not in self._graph:
                return None
            return self._to_node(key)

    def _to_node(self, key: str) -> GraphNode:
        data = dict(self._graph.nodes[key])
        label = data.pop("label", "Unknown")
        name = data.pop("name", key.split(":", 1)[-1])
        return GraphNode(label=label, key=key, name=name, properties=data)

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
        with self._lock:
            if start_key not in self._graph:
                return []
            relation_filter = set(relations) if relations else None
            label_filter = set(labels) if labels else None

            results: list[GraphPath] = []
            visited: set[str] = {start_key}
            queue: deque[tuple[str, int, float, list[str], str]] = deque([(start_key, 0, 1.0, [], "")])

            while queue and len(results) < limit:
                key, level, weight, via, _ = queue.popleft()
                if level >= depth:
                    continue
                edges = list(self._graph.out_edges(key, data=True))
                if undirected:
                    edges += [(key, source, data) for source, _, data in self._graph.in_edges(key, data=True)]
                for _, target, data in edges:
                    relation = data.get("relation", "RELATED_TO")
                    if relation_filter and relation not in relation_filter:
                        continue
                    if target in visited:
                        continue
                    visited.add(target)
                    node = self._to_node(target)
                    edge_weight = round(weight * float(data.get("weight", 1.0) or 1.0), 4)
                    path_via = [*via, self._graph.nodes[key].get("name", key)]
                    if label_filter is None or node.label in label_filter:
                        results.append(
                            GraphPath(node=node, relation=relation, depth=level + 1, weight=edge_weight, via=path_via)
                        )
                    queue.append((target, level + 1, edge_weight, path_via, relation))

            results.sort(key=lambda path: (-path.weight, path.depth))
            return results[:limit]

    def neighbours(
        self, key: str, *, relations: list[str] | None = None, labels: list[str] | None = None, limit: int = 200
    ) -> list[GraphPath]:
        with self._lock:
            if key not in self._graph:
                return []
            relation_filter = set(relations) if relations else None
            label_filter = set(labels) if labels else None
            paths: list[GraphPath] = []
            seen: set[tuple[str, str]] = set()

            for source, target, data in list(self._graph.out_edges(key, data=True)) + [
                (target, source, data) for target, source, data in self._graph.in_edges(key, data=True)
            ]:
                other = target if source == key else source
                relation = data.get("relation", "RELATED_TO")
                if relation_filter and relation not in relation_filter:
                    continue
                if (other, relation) in seen or other == key:
                    continue
                node = self._to_node(other)
                if label_filter and node.label not in label_filter:
                    continue
                seen.add((other, relation))
                paths.append(
                    GraphPath(
                        node=node,
                        relation=relation,
                        depth=1,
                        weight=float(data.get("weight", 1.0) or 1.0),
                        via=[self._graph.nodes[key].get("name", key)],
                    )
                )
            paths.sort(key=lambda path: -path.weight)
            return paths[:limit]

    def subgraph(self, keys: list[str], *, depth: int = 1, limit: int = 400) -> tuple[list[GraphNode], list[GraphEdge]]:
        with self._lock:
            selected: set[str] = set()
            for key in keys:
                if key not in self._graph:
                    continue
                selected.add(key)
                for path in self.traverse(key, depth=depth, limit=limit):
                    selected.add(path.node.key)
                if len(selected) >= limit:
                    break

            nodes = [self._to_node(key) for key in list(selected)[:limit]]
            node_set = {node.key for node in nodes}
            edges = [
                GraphEdge(
                    source_key=source,
                    target_key=target,
                    relation=data.get("relation", "RELATED_TO"),
                    weight=float(data.get("weight", 1.0) or 1.0),
                )
                for source, target, data in self._graph.edges(data=True)
                if source in node_set and target in node_set
            ]
            return nodes, edges

    def find_candidates_by_skills(self, skill_keys: list[str], *, limit: int = 500) -> dict[str, list[str]]:
        with self._lock:
            found: dict[str, list[str]] = {}
            for skill_key in skill_keys:
                if skill_key not in self._graph:
                    continue
                for source, _, data in self._graph.in_edges(skill_key, data=True):
                    if data.get("relation") != "HAS_SKILL":
                        continue
                    if not source.startswith("Candidate:"):
                        continue
                    found.setdefault(source, []).append(skill_key)
                    if len(found) >= limit:
                        break
            return found

    def stats(self) -> GraphStats:
        with self._lock:
            labels = Counter(data.get("label", "Unknown") for _, data in self._graph.nodes(data=True))
            relations = Counter(data.get("relation", "UNKNOWN") for _, _, data in self._graph.edges(data=True))
            return GraphStats(
                backend=self.name,
                node_count=self._graph.number_of_nodes(),
                edge_count=self._graph.number_of_edges(),
                node_counts=dict(labels),
                relationship_counts=dict(relations),
                healthy=True,
                detail="in-process networkx graph",
            )

    # -------------------------------------------------------------- extensions
    def centrality(self, label: str | None = None, top_k: int = 20) -> list[tuple[str, float]]:
        """Degree centrality, used to surface hub skills/technologies in reports."""
        with self._lock:
            if self._graph.number_of_nodes() == 0:
                return []
            scores = nx.degree_centrality(self._graph)
            items = [
                (self._graph.nodes[key].get("name", key), value)
                for key, value in scores.items()
                if label is None or self._graph.nodes[key].get("label") == label
            ]
            items.sort(key=lambda item: -item[1])
            return items[:top_k]

    def shortest_path(self, source_key: str, target_key: str) -> list[GraphNode]:
        with self._lock:
            if source_key not in self._graph or target_key not in self._graph:
                return []
            try:
                keys = nx.shortest_path(self._graph.to_undirected(as_view=True), source_key, target_key)
            except nx.NetworkXNoPath:
                return []
            return [self._to_node(key) for key in keys]
