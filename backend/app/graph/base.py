"""Graph backend abstraction shared by the Neo4j and NetworkX implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.ai.text_utils import normalize_key


def node_key(label: str, identifier: str | int) -> str:
    """Stable, backend-independent node identity, e.g. ``Skill:reactjs``."""
    if isinstance(identifier, int):
        return f"{label}:{identifier}"
    normalized = normalize_key(str(identifier)) or str(identifier).strip().lower()
    return f"{label}:{normalized}"


@dataclass(slots=True)
class GraphNode:
    label: str
    key: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, label: str, identifier: str | int, name: str, **properties: Any) -> GraphNode:
        return cls(label=label, key=node_key(label, identifier), name=name, properties=properties)


@dataclass(slots=True)
class GraphEdge:
    source_key: str
    target_key: str
    relation: str
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphPath:
    """A traversal result: the reached node plus how it was reached."""

    node: GraphNode
    relation: str
    depth: int
    weight: float
    via: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphStats:
    backend: str
    node_count: int
    edge_count: int
    node_counts: dict[str, int] = field(default_factory=dict)
    relationship_counts: dict[str, int] = field(default_factory=dict)
    healthy: bool = True
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_counts": self.node_counts,
            "relationship_counts": self.relationship_counts,
            "healthy": self.healthy,
            "detail": self.detail,
        }


class GraphBackend(ABC):
    """Minimal graph API required by the Graph RAG engine."""

    name: str = "base"

    @abstractmethod
    def upsert_nodes(self, nodes: list[GraphNode]) -> int: ...

    @abstractmethod
    def upsert_edges(self, edges: list[GraphEdge]) -> int: ...

    @abstractmethod
    def delete_node(self, key: str) -> None: ...

    @abstractmethod
    def delete_edges_from(self, key: str, relations: list[str] | None = None) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def get_node(self, key: str) -> GraphNode | None: ...

    @abstractmethod
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
        """Breadth-first walk with multiplicative weight decay.

        ``undirected=True`` also walks edges backwards, which is what reaches
        candidates from a skill (``Candidate -[HAS_SKILL]-> Skill``).
        """

    @abstractmethod
    def neighbours(
        self, key: str, *, relations: list[str] | None = None, labels: list[str] | None = None, limit: int = 200
    ) -> list[GraphPath]: ...

    @abstractmethod
    def subgraph(self, keys: list[str], *, depth: int = 1, limit: int = 400) -> tuple[list[GraphNode], list[GraphEdge]]:
        ...

    @abstractmethod
    def find_candidates_by_skills(self, skill_keys: list[str], *, limit: int = 500) -> dict[str, list[str]]:
        """Return ``{candidate_key: [matched skill keys]}`` for the given skills."""

    @abstractmethod
    def stats(self) -> GraphStats: ...

    def health(self) -> bool:
        try:
            return self.stats().healthy
        except Exception:
            return False
