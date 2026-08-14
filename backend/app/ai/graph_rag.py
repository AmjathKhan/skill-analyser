"""Graph RAG engine: graph traversal + vector retrieval + context building.

Pipeline (mirrors the architecture diagram):

1. Resolve the recruiter query against the skill taxonomy.
2. Expand each skill through the knowledge graph (hierarchy, related skills,
   technologies, job roles) to obtain the *semantic neighbourhood*.
3. Retrieve candidates two ways - graph traversal (``Candidate-HAS_SKILL->Skill``
   including expanded skills) and vector similarity over resume embeddings.
4. Fuse both channels into a single candidate set with retrieval provenance.
5. Build a compact, human-readable context that feeds scoring and LLM reasoning.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.embeddings import build_requirement_document, get_embedder
from app.ai.text_utils import normalize_key, truncate
from app.ai.vector_store import VectorHit, get_vector_store
from app.core.constants import EmbeddingKind, NodeLabel, RelationType
from app.core.logging import get_logger
from app.graph.base import GraphBackend, GraphPath, node_key
from app.graph.builder import candidate_key, skill_key
from app.graph.registry import get_graph
from app.models.candidate import Candidate, CandidateSkill
from app.schemas.matching import GraphContextSummary
from app.services.taxonomy import ExpandedSkill, SkillNode, SkillTaxonomy, TaxonomyMatch, get_taxonomy

logger = get_logger(__name__)

EXPERIENCE_IN_QUERY_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
LOCATION_IN_QUERY_RE = re.compile(r"\b(?:in|at|from|based\s+in)\s+([A-Z][a-zA-Z ]{2,30})")


@dataclass(slots=True)
class ParsedQuery:
    raw: str
    skills: list[TaxonomyMatch] = field(default_factory=list)
    unknown_terms: list[str] = field(default_factory=list)
    min_experience_years: float | None = None
    location: str | None = None

    @property
    def skill_names(self) -> list[str]:
        return [match.skill.name for match in self.skills]


@dataclass(slots=True)
class CandidateRetrieval:
    candidate_id: int
    graph_score: float = 0.0
    vector_score: float = 0.0
    matched_skill_ids: set[int] = field(default_factory=set)
    matched_skill_keys: set[str] = field(default_factory=set)
    channels: set[str] = field(default_factory=set)
    snippets: list[str] = field(default_factory=list)

    @property
    def fused_score(self) -> float:
        return round(0.65 * self.graph_score + 0.35 * self.vector_score, 4)


@dataclass(slots=True)
class Retrieval:
    query: ParsedQuery
    requested_skills: list[TaxonomyMatch] = field(default_factory=list)
    unresolved_skills: list[str] = field(default_factory=list)
    expansions: dict[int, list[ExpandedSkill]] = field(default_factory=dict)
    candidates: dict[int, CandidateRetrieval] = field(default_factory=dict)
    vector_hits: list[VectorHit] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    graph_backend: str = "networkx"

    def candidate_ids(self, limit: int | None = None) -> list[int]:
        ordered = sorted(self.candidates.values(), key=lambda item: -item.fused_score)
        ids = [item.candidate_id for item in ordered]
        return ids[:limit] if limit else ids

    def expanded_ids_for(self, skill_id: int) -> dict[int, ExpandedSkill]:
        return {item.skill.id: item for item in self.expansions.get(skill_id, [])}


class GraphRAGEngine:
    def __init__(self, session: Session, graph: GraphBackend | None = None) -> None:
        self.session = session
        self.graph = graph or get_graph()
        self.taxonomy: SkillTaxonomy = get_taxonomy(session)
        self.vector_store = get_vector_store()

    # -------------------------------------------------------------- query parse
    def parse_query(self, text: str) -> ParsedQuery:
        """Turn ``"Python React PostgreSQL FastAPI 5 years"`` into structured intent."""
        raw = (text or "").strip()
        parsed = ParsedQuery(raw=raw)
        if not raw:
            return parsed

        experience_match = EXPERIENCE_IN_QUERY_RE.search(raw)
        if experience_match:
            parsed.min_experience_years = float(experience_match.group(1))

        stripped = EXPERIENCE_IN_QUERY_RE.sub(" ", raw)
        parsed.skills = self.taxonomy.scan_text(stripped)
        parsed.location = self._parse_location(stripped)

        matched_keys = {normalize_key(match.matched_text) for match in parsed.skills}
        matched_keys |= {match.skill.normalized for match in parsed.skills}
        for token in re.split(r"[,;/|]|\s{2,}", stripped):
            token = token.strip()
            if not token or len(token) < 2:
                continue
            if normalize_key(token) in matched_keys:
                continue
            resolved = self.taxonomy.resolve(token)
            if resolved:
                if resolved.skill.id not in {match.skill.id for match in parsed.skills}:
                    parsed.skills.append(resolved)
            elif len(token.split()) <= 4 and not token.isdigit():
                parsed.unknown_terms.append(token)
        return parsed

    def _parse_location(self, text: str) -> str | None:
        """Read a place name out of ``in <Place>``, ignoring technologies.

        ``"Python developer in Kubernetes"`` must not filter candidates by a city
        called Kubernetes, so any phrase the taxonomy recognises is discarded.
        """
        for match in LOCATION_IN_QUERY_RE.finditer(text):
            phrase = match.group(1).strip(" ,.;")
            while phrase:
                if not self.taxonomy.resolve(phrase, allow_fuzzy=False):
                    return phrase
                # Trailing words may be the real place: "in Kubernetes Bengaluru".
                parts = phrase.split()
                if len(parts) == 1:
                    break
                phrase = " ".join(parts[1:])
        return None

    # ----------------------------------------------------------------- retrieve
    def retrieve(
        self,
        *,
        skills: Iterable[str],
        query_text: str | None = None,
        min_experience_years: float | None = None,
        preferred_certifications: Iterable[str] = (),
        preferred_domain: str | None = None,
        job_title: str | None = None,
        job_description: str | None = None,
        expansion_depth: int = 2,
        top_k: int = 100,
        candidate_ids: Iterable[int] | None = None,
    ) -> Retrieval:
        parsed = self.parse_query(query_text or " ".join(skills))
        if min_experience_years is not None:
            parsed.min_experience_years = min_experience_years

        requested: list[TaxonomyMatch] = []
        unresolved: list[str] = []
        seen_ids: set[int] = set()
        for phrase in skills:
            match = self.taxonomy.resolve(phrase)
            if match and match.skill.id not in seen_ids:
                seen_ids.add(match.skill.id)
                requested.append(match)
            elif not match:
                unresolved.append(phrase)

        retrieval = Retrieval(
            query=parsed,
            requested_skills=requested,
            unresolved_skills=unresolved,
            graph_backend=self.graph.name,
        )

        # --- Step 2: expand the skill neighbourhood through the graph ---
        for match in requested:
            expanded = self.taxonomy.expand(match.skill.id, depth=expansion_depth)
            retrieval.expansions[match.skill.id] = expanded
            for item in expanded[:6]:
                retrieval.paths.append(
                    f"{match.skill.name} -[{item.relation}]-> {item.skill.name} (w={item.weight})"
                )

        allowed_ids = {int(value) for value in candidate_ids} if candidate_ids is not None else None

        # --- Step 3a: graph retrieval ---
        direct_keys = {skill_key(match.skill.name): match.skill.id for match in requested}
        expanded_keys: dict[str, tuple[int, float]] = {}
        for expansions in retrieval.expansions.values():
            for item in expansions:
                key = skill_key(item.skill.name)
                if key in direct_keys:
                    continue
                current = expanded_keys.get(key)
                if current is None or item.weight > current[1]:
                    expanded_keys[key] = (item.skill.id, item.weight)

        graph_hits = self.graph.find_candidates_by_skills(
            list(direct_keys) + list(expanded_keys), limit=max(top_k * 5, 200)
        )
        total_weight = max(1.0, len(direct_keys) + 0.5 * len(expanded_keys))
        for graph_candidate_key, matched_keys in graph_hits.items():
            candidate_id = _candidate_id_from_key(graph_candidate_key)
            if candidate_id is None or (allowed_ids is not None and candidate_id not in allowed_ids):
                continue
            score = 0.0
            matched_skill_ids: set[int] = set()
            for key in matched_keys:
                if key in direct_keys:
                    score += 1.0
                    matched_skill_ids.add(direct_keys[key])
                elif key in expanded_keys:
                    skill_id, weight = expanded_keys[key]
                    score += 0.5 * weight
                    matched_skill_ids.add(skill_id)
            entry = retrieval.candidates.setdefault(candidate_id, CandidateRetrieval(candidate_id=candidate_id))
            entry.graph_score = round(min(1.0, score / total_weight), 4)
            entry.matched_skill_ids |= matched_skill_ids
            entry.matched_skill_keys |= set(matched_keys)
            entry.channels.add("graph")

        # --- Step 3b: vector retrieval ---
        document = build_requirement_document(
            title=job_title,
            required_skills=[match.skill.name for match in requested] or list(skills),
            preferred_skills=[],
            certifications=list(preferred_certifications),
            min_experience=parsed.min_experience_years,
            domain=preferred_domain,
            description=job_description or parsed.raw,
        )
        query_vector = get_embedder().encode(document)
        hits = self.vector_store.search(
            self.session,
            query_vector,
            top_k=max(top_k * 2, 50),
            kinds=[EmbeddingKind.RESUME.value, EmbeddingKind.RESUME_CHUNK.value],
            candidate_ids=sorted(allowed_ids) if allowed_ids is not None else None,
        )
        retrieval.vector_hits = hits
        for hit in hits:
            if hit.candidate_id is None:
                continue
            entry = retrieval.candidates.setdefault(
                hit.candidate_id, CandidateRetrieval(candidate_id=hit.candidate_id)
            )
            entry.vector_score = max(entry.vector_score, round(max(0.0, hit.score), 4))
            entry.channels.add("vector")
            if hit.text_snippet:
                entry.snippets.append(truncate(hit.text_snippet, 240))

        if retrieval.paths:
            logger.debug("graph expansion produced %s paths", len(retrieval.paths))
        return retrieval

    # ------------------------------------------------------------------ context
    def candidate_graph_context(
        self,
        candidate_id: int,
        *,
        requested_skills: Iterable[str] = (),
        include_similar: bool = True,
        depth: int = 2,
    ) -> GraphContextSummary:
        """Neighbourhood of one candidate, used for explanations and the profile page."""
        summary = GraphContextSummary()
        key = candidate_key(candidate_id)

        neighbours = self.graph.neighbours(key, limit=300)
        skill_names: list[str] = []
        for path in neighbours:
            label = path.node.label
            if label == NodeLabel.SKILL.value:
                skill_names.append(path.node.name)
            elif label == NodeLabel.COMPANY.value:
                summary.companies.append(path.node.name)
            elif label == NodeLabel.CERTIFICATION.value:
                summary.certifications.append(path.node.name)
        summary.connected_skills = list(dict.fromkeys(skill_names))[:60]

        technologies: list[str] = []
        job_roles: list[str] = []
        hierarchy: list[dict[str, str]] = []
        for name in summary.connected_skills[:25]:
            node = self.taxonomy.by_name(name)
            if node is None:
                continue
            if node.technology_stack:
                technologies.append(node.technology_stack)
            job_roles.extend(node.job_roles)
            if node.parent_id:
                parent = self.taxonomy.get(node.parent_id)
                if parent:
                    hierarchy.append({"skill": node.name, "parent": parent.name, "relation": "DEPENDS_ON"})
        summary.related_technologies = list(dict.fromkeys(technologies))[:20]
        summary.job_roles = list(dict.fromkeys(job_roles))[:20]
        summary.skill_hierarchy = hierarchy[:20]

        for requested in requested_skills:
            match = self.taxonomy.resolve(requested)
            if not match:
                continue
            for expanded in self.taxonomy.expand(match.skill.id, depth=1)[:8]:
                if expanded.skill.name in summary.connected_skills:
                    summary.equivalent_skills.append(
                        {
                            "requested": match.skill.name,
                            "candidate_has": expanded.skill.name,
                            "relation": expanded.relation,
                        }
                    )

        summary.retrieval_paths = [
            f"Candidate -[{path.relation}]-> {path.node.name}" for path in neighbours[:25]
        ]

        if include_similar:
            summary.similar_candidates = self.similar_candidates(candidate_id, limit=5)
        return summary

    def similar_candidates(self, candidate_id: int, *, limit: int = 5) -> list[dict[str, Any]]:
        """Candidates sharing the most skills, via graph co-occurrence."""
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            return []
        names_by_key: dict[str, str] = {}
        for link in candidate.skills:
            name = link.skill.name if link.skill else link.raw_text
            names_by_key[skill_key(name)] = name
        if not names_by_key:
            return []

        overlaps = self.graph.find_candidates_by_skills(list(names_by_key), limit=400)
        scored: list[tuple[int, set[str]]] = []
        for other_key, matched in overlaps.items():
            other_id = _candidate_id_from_key(other_key)
            if other_id is None or other_id == candidate_id:
                continue
            scored.append((other_id, set(matched)))
        scored.sort(key=lambda item: -len(item[1]))

        results: list[dict[str, Any]] = []
        denominator = max(1, len(names_by_key))
        for other_id, shared in scored[:limit]:
            other = self.session.get(Candidate, other_id)
            if other is None or other.is_deleted:
                continue
            results.append(
                {
                    "candidate_id": other.id,
                    "candidate_uuid": other.uuid,
                    "full_name": other.full_name,
                    "current_title": other.current_title,
                    "shared_skills": len(shared),
                    "shared_skill_names": sorted(names_by_key[key] for key in shared if key in names_by_key),
                    "similarity_percent": round(min(1.0, len(shared) / denominator) * 100, 1),
                    "total_experience_years": other.total_experience_years,
                }
            )
        return results

    def skill_neighbourhood(self, skill_name: str, *, depth: int = 2, limit: int = 60) -> list[GraphPath]:
        return self.graph.traverse(skill_key(skill_name), depth=depth, limit=limit)

    def build_context_text(
        self,
        *,
        candidate: Candidate,
        requested_skills: Iterable[str],
        matched: Iterable[str],
        missing: Iterable[str],
        related: Iterable[str],
        graph_context: GraphContextSummary,
        snippets: Iterable[str] = (),
    ) -> str:
        """Compact grounding context handed to the LLM (or the template writer)."""
        lines = [
            f"Candidate: {candidate.full_name}",
            f"Current role: {candidate.current_title or 'unknown'} at {candidate.current_company_name or 'unknown'}",
            f"Total experience: {candidate.total_experience_years} years",
            f"Education: {candidate.highest_degree or 'not stated'}",
            f"Location: {', '.join(part for part in [candidate.city, candidate.country] if part) or 'not stated'}",
            f"Requested skills: {', '.join(requested_skills) or 'none'}",
            f"Matched skills: {', '.join(matched) or 'none'}",
            f"Related/transferable skills: {', '.join(related) or 'none'}",
            f"Missing skills: {', '.join(missing) or 'none'}",
        ]
        if graph_context.equivalent_skills:
            equivalents = "; ".join(
                f"{item['requested']} ~ {item['candidate_has']} ({item['relation']})"
                for item in graph_context.equivalent_skills[:8]
            )
            lines.append(f"Graph equivalences: {equivalents}")
        if graph_context.companies:
            lines.append(f"Companies: {', '.join(graph_context.companies[:6])}")
        if graph_context.certifications:
            lines.append(f"Certifications: {', '.join(graph_context.certifications[:6])}")
        if graph_context.retrieval_paths:
            lines.append("Graph paths: " + " | ".join(graph_context.retrieval_paths[:8]))
        snippet_list = [snippet for snippet in snippets if snippet][:3]
        if snippet_list:
            lines.append("Resume evidence: " + " || ".join(snippet_list))
        return "\n".join(lines)

    # ------------------------------------------------------------------- helpers
    def load_candidates(self, candidate_ids: Iterable[int]) -> list[Candidate]:
        ids = [int(value) for value in candidate_ids]
        if not ids:
            return []
        return list(
            self.session.scalars(
                select(Candidate)
                .where(Candidate.id.in_(ids), Candidate.is_deleted.is_(False))
                .options(
                    selectinload(Candidate.skills).selectinload(CandidateSkill.skill),
                    selectinload(Candidate.experiences),
                    selectinload(Candidate.projects),
                    selectinload(Candidate.certifications),
                    selectinload(Candidate.educations),
                )
            )
        )

    def technology_neighbours(self, technology: str, *, limit: int = 30) -> list[str]:
        paths = self.graph.neighbours(
            node_key(NodeLabel.TECHNOLOGY.value, technology),
            relations=[RelationType.DEPENDS_ON.value, RelationType.PART_OF.value, RelationType.USES.value],
            limit=limit,
        )
        return [path.node.name for path in paths]


def _candidate_id_from_key(key: str) -> int | None:
    if not key.startswith(f"{NodeLabel.CANDIDATE.value}:"):
        return None
    try:
        return int(key.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def skill_nodes_from_matches(matches: Iterable[TaxonomyMatch]) -> list[SkillNode]:
    return [match.skill for match in matches]
