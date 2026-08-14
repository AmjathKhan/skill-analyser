"""In-memory index over the Skills knowledge base.

The CSV loaded into PostgreSQL is the authoritative taxonomy. This module turns
it into a fast lookup structure that can:

* resolve a raw resume phrase to a canonical skill (exact / synonym / fuzzy),
* scan free text for skill mentions using n-gram lookup,
* expand a skill into parents, children and related skills for graph retrieval.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.text_utils import ngrams, normalize_key, similarity, tokenize
from app.core.logging import get_logger
from app.models.skill import Skill, SkillRelation

logger = get_logger(__name__)

#: Short names that would otherwise match ordinary words: require an exact,
#: case-sensitive token match ("Go" the language vs. the verb "go").
AMBIGUOUS_NAMES = {"go", "r", "c", "d", "ms", "ai", "ml", "dl", "cv", "sa", "ag", "bv"}

FUZZY_THRESHOLD = 0.90
MAX_NGRAM = 4


@dataclass(slots=True)
class SkillNode:
    id: int
    name: str
    normalized: str
    slug: str
    category: str | None
    parent_id: int | None
    technology_stack: str | None
    experience_level: str | None
    description: str | None
    is_technical: bool
    synonyms: tuple[str, ...] = ()
    related_ids: tuple[int, ...] = ()
    child_ids: tuple[int, ...] = ()
    job_roles: tuple[str, ...] = ()


@dataclass(slots=True)
class TaxonomyMatch:
    skill: SkillNode
    matched_text: str
    #: exact | synonym | fuzzy
    match_type: str
    confidence: float
    evidence: str | None = None


@dataclass(slots=True)
class ExpandedSkill:
    skill: SkillNode
    relation: str
    weight: float
    via: str | None = None


class SkillTaxonomy:
    """Snapshot of the skill graph; rebuilt whenever the CSV is re-imported."""

    def __init__(self) -> None:
        self._nodes: dict[int, SkillNode] = {}
        self._by_key: dict[str, int] = {}
        self._by_synonym: dict[str, int] = {}
        self._by_name: dict[str, int] = {}
        self._categories: dict[str, list[int]] = {}
        self._loaded = False

    # ------------------------------------------------------------------- build
    def load(self, session: Session) -> None:
        skills = list(
            session.scalars(
                select(Skill).options(
                    selectinload(Skill.synonyms),
                    selectinload(Skill.category),
                    selectinload(Skill.job_roles),
                )
            )
        )
        relations = list(session.scalars(select(SkillRelation)))

        related_map: dict[int, set[int]] = {}
        for relation in relations:
            related_map.setdefault(relation.source_skill_id, set()).add(relation.target_skill_id)
            related_map.setdefault(relation.target_skill_id, set()).add(relation.source_skill_id)

        children: dict[int, set[int]] = {}
        for skill in skills:
            if skill.parent_skill_id:
                children.setdefault(skill.parent_skill_id, set()).add(skill.id)

        nodes: dict[int, SkillNode] = {}
        by_key: dict[str, int] = {}
        by_synonym: dict[str, int] = {}
        by_name: dict[str, int] = {}
        categories: dict[str, list[int]] = {}

        for skill in skills:
            synonyms = tuple(sorted({synonym.synonym for synonym in skill.synonyms}))
            node = SkillNode(
                id=skill.id,
                name=skill.name,
                normalized=skill.normalized_name or normalize_key(skill.name),
                slug=skill.slug,
                category=skill.category.name if skill.category else None,
                parent_id=skill.parent_skill_id,
                technology_stack=skill.technology_stack,
                experience_level=skill.experience_level,
                description=skill.description,
                is_technical=skill.is_technical,
                synonyms=synonyms,
                related_ids=tuple(sorted(related_map.get(skill.id, set()))),
                child_ids=tuple(sorted(children.get(skill.id, set()))),
                job_roles=tuple(role.name for role in skill.job_roles),
            )
            nodes[skill.id] = node
            by_key[node.normalized] = skill.id
            by_name[skill.name.lower()] = skill.id
            for synonym in synonyms:
                key = normalize_key(synonym)
                if key and key not in by_key:
                    by_synonym.setdefault(key, skill.id)
            if node.category:
                categories.setdefault(node.category, []).append(skill.id)

        self._nodes = nodes
        self._by_key = by_key
        self._by_synonym = by_synonym
        self._by_name = by_name
        self._categories = categories
        self._loaded = True
        logger.info("skill taxonomy loaded: %s skills, %s synonyms", len(nodes), len(by_synonym))

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def size(self) -> int:
        return len(self._nodes)

    def all_skills(self) -> list[SkillNode]:
        return list(self._nodes.values())

    def get(self, skill_id: int) -> SkillNode | None:
        return self._nodes.get(skill_id)

    def by_name(self, name: str) -> SkillNode | None:
        skill_id = self._by_name.get((name or "").lower())
        return self._nodes.get(skill_id) if skill_id else None

    def categories(self) -> dict[str, list[SkillNode]]:
        return {
            category: [self._nodes[skill_id] for skill_id in ids if skill_id in self._nodes]
            for category, ids in self._categories.items()
        }

    # ----------------------------------------------------------------- resolve
    def resolve(self, phrase: str, *, allow_fuzzy: bool = True) -> TaxonomyMatch | None:
        """Map a raw phrase onto a canonical skill."""
        raw = (phrase or "").strip()
        if not raw:
            return None
        key = normalize_key(raw)
        if not key:
            return None

        if key in AMBIGUOUS_NAMES:
            skill_id = self._by_key.get(key) or self._by_synonym.get(key)
            node = self._nodes.get(skill_id) if skill_id else None
            if node and raw.strip() == node.name:
                return TaxonomyMatch(node, raw, "exact", 1.0)
            return None

        skill_id = self._by_key.get(key)
        if skill_id:
            return TaxonomyMatch(self._nodes[skill_id], raw, "exact", 1.0)

        skill_id = self._by_synonym.get(key)
        if skill_id:
            return TaxonomyMatch(self._nodes[skill_id], raw, "synonym", 0.95)

        if not allow_fuzzy or len(key) < 4:
            return None

        best_node: SkillNode | None = None
        best_score = 0.0
        for candidate_key, candidate_id in self._by_key.items():
            if abs(len(candidate_key) - len(key)) > 4:
                continue
            score = similarity(candidate_key, key)
            if score > best_score:
                best_score, best_node = score, self._nodes[candidate_id]
        if best_node and best_score >= FUZZY_THRESHOLD:
            return TaxonomyMatch(best_node, raw, "fuzzy", round(best_score * 0.9, 3))
        return None

    def scan_text(self, text: str, *, evidence_window: int = 140) -> list[TaxonomyMatch]:
        """Find every taxonomy skill mentioned in free text via n-gram lookup."""
        if not text:
            return []
        matches: dict[int, TaxonomyMatch] = {}
        for line in text.split("\n"):
            tokens = tokenize(line, drop_stopwords=False)
            if not tokens:
                continue
            original_tokens = line.split()
            for phrase in ngrams(tokens, MAX_NGRAM):
                key = normalize_key(phrase)
                if not key:
                    continue
                skill_id = self._by_key.get(key) or self._by_synonym.get(key)
                if not skill_id:
                    continue
                node = self._nodes.get(skill_id)
                if node is None:
                    continue
                if key in AMBIGUOUS_NAMES and node.name not in original_tokens:
                    continue
                existing = matches.get(skill_id)
                confidence = 1.0 if key == node.normalized else 0.95
                if existing is None or confidence > existing.confidence:
                    matches[skill_id] = TaxonomyMatch(
                        node,
                        phrase,
                        "exact" if key == node.normalized else "synonym",
                        confidence,
                        evidence=line[:evidence_window],
                    )
        return list(matches.values())

    # ------------------------------------------------------------------ expand
    def expand(self, skill_id: int, *, depth: int = 1, include_children: bool = True) -> list[ExpandedSkill]:
        """Graph traversal around a skill: parents, children and related skills."""
        node = self._nodes.get(skill_id)
        if node is None:
            return []

        seen: set[int] = {skill_id}
        results: list[ExpandedSkill] = []
        frontier: list[tuple[SkillNode, int, float, str | None]] = [(node, 0, 1.0, None)]

        while frontier:
            current, level, weight, via = frontier.pop(0)
            if level >= depth:
                continue
            neighbours: list[tuple[int, str, float]] = []
            if current.parent_id:
                neighbours.append((current.parent_id, "PARENT_OF", 0.75))
            if include_children:
                neighbours.extend((child_id, "PARENT_OF", 0.7) for child_id in current.child_ids)
            neighbours.extend((related_id, "RELATED_TO", 0.6) for related_id in current.related_ids)

            for neighbour_id, relation, edge_weight in neighbours:
                if neighbour_id in seen:
                    continue
                neighbour = self._nodes.get(neighbour_id)
                if neighbour is None:
                    continue
                seen.add(neighbour_id)
                score = round(weight * edge_weight, 4)
                results.append(ExpandedSkill(neighbour, relation, score, via or current.name))
                frontier.append((neighbour, level + 1, score, current.name))

        results.sort(key=lambda item: item.weight, reverse=True)
        return results

    def equivalent_ids(self, skill_id: int) -> set[int]:
        """Skills close enough to count as partial credit when matching."""
        node = self._nodes.get(skill_id)
        if node is None:
            return set()
        ids = set(node.related_ids) | set(node.child_ids)
        if node.parent_id:
            ids.add(node.parent_id)
        return ids

    def resolve_many(self, phrases: Iterable[str]) -> list[TaxonomyMatch]:
        results: list[TaxonomyMatch] = []
        seen: set[int] = set()
        for phrase in phrases:
            match = self.resolve(phrase)
            if match and match.skill.id not in seen:
                seen.add(match.skill.id)
                results.append(match)
        return results


_taxonomy = SkillTaxonomy()
_lock = threading.Lock()


def get_taxonomy(session: Session, *, refresh: bool = False) -> SkillTaxonomy:
    """Return the process-wide taxonomy snapshot, loading it on first use."""
    global _taxonomy
    if refresh or not _taxonomy.is_loaded:
        with _lock:
            if refresh or not _taxonomy.is_loaded:
                _taxonomy.load(session)
    return _taxonomy


def invalidate_taxonomy() -> None:
    """Called after a CSV import so the next request rebuilds the snapshot."""
    global _taxonomy
    with _lock:
        _taxonomy = SkillTaxonomy()
