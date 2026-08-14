"""Candidate search: semantic, keyword, graph, skill and hybrid modes."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.graph_rag import GraphRAGEngine
from app.ai.reasoning import answer_with_context
from app.ai.text_utils import normalize_key, tokenize, truncate
from app.core.logging import get_logger
from app.models.candidate import Candidate
from app.repositories import candidate_repository as repo
from app.schemas.candidate import CandidateFilters
from app.schemas.search import (
    MatchedSkillHit,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SuggestResponse,
)

logger = get_logger(__name__)

CHANNEL_WEIGHTS = {
    "hybrid": {"graph": 0.45, "semantic": 0.35, "keyword": 0.20},
    "semantic": {"graph": 0.0, "semantic": 1.0, "keyword": 0.0},
    "graph": {"graph": 1.0, "semantic": 0.0, "keyword": 0.0},
    "skill": {"graph": 1.0, "semantic": 0.0, "keyword": 0.0},
    "keyword": {"graph": 0.0, "semantic": 0.0, "keyword": 1.0},
}


class SearchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.rag = GraphRAGEngine(session)

    def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        parsed = self.rag.parse_query(request.query)

        requested_skills = list(dict.fromkeys([*parsed.skill_names, *(request.filters.skills or [])]))
        min_experience = request.filters.min_experience
        if min_experience is None and parsed.min_experience_years:
            min_experience = parsed.min_experience_years

        graph_scores: dict[int, float] = {}
        semantic_scores: dict[int, float] = {}
        snippets: dict[int, str] = {}
        matched_skill_ids: dict[int, set[int]] = {}
        channels: dict[int, set[str]] = {}
        expanded_view: list[dict[str, str]] = []
        graph_paths: list[str] = []

        if request.mode != "keyword" and (requested_skills or request.query.strip()):
            retrieval = self.rag.retrieve(
                skills=requested_skills,
                query_text=request.query,
                min_experience_years=min_experience,
                top_k=max(request.page_size * 5, 100),
            )
            graph_paths = retrieval.paths[:20]
            for skill_id, expansions in retrieval.expansions.items():
                source = self.rag.taxonomy.get(skill_id)
                for item in expansions[:5]:
                    expanded_view.append(
                        {
                            "skill": source.name if source else str(skill_id),
                            "related": item.skill.name,
                            "relation": item.relation,
                            "weight": str(item.weight),
                        }
                    )
            for candidate_id, entry in retrieval.candidates.items():
                graph_scores[candidate_id] = entry.graph_score
                semantic_scores[candidate_id] = entry.vector_score
                matched_skill_ids[candidate_id] = set(entry.matched_skill_ids)
                channels[candidate_id] = set(entry.channels)
                if entry.snippets:
                    snippets[candidate_id] = entry.snippets[0]

        weights = CHANNEL_WEIGHTS.get(request.mode, CHANNEL_WEIGHTS["hybrid"])

        # Filtering happens in SQL; retrieval only orders the pool.
        filters = CandidateFilters(
            search=request.query if request.mode in {"keyword", "hybrid"} else None,
            # Free text queries carry filler words, so any matching term qualifies;
            # the keyword score below decides the ranking.
            search_mode="any",
            status=request.filters.status,
            skills=request.filters.skills if request.mode == "skill" else None,
            min_experience=min_experience,
            max_experience=request.filters.max_experience,
            location=request.filters.location or parsed.location,
            company=request.filters.current_company,
            education=request.filters.education,
            certification=request.filters.certification,
            technology=request.filters.technology,
            availability=request.filters.availability,
            page=1,
            page_size=500,
            sort_by="created_at",
            sort_dir="desc",
        )
        if request.mode in {"semantic", "graph"} and (graph_scores or semantic_scores):
            filters.candidate_ids = list({*graph_scores, *semantic_scores})
            filters.search = None

        pool, _ = repo.list_candidates(self.session, filters)

        if request.mode == "hybrid" and (graph_scores or semantic_scores):
            # Hybrid: union of keyword hits and retrieval hits (both are filtered again below).
            retrieved_only = [
                candidate_id
                for candidate_id in {*graph_scores, *semantic_scores}
                if candidate_id not in {candidate.id for candidate in pool}
            ]
            if retrieved_only:
                extra_filters = filters.model_copy(update={"search": None, "candidate_ids": retrieved_only})
                extra, _ = repo.list_candidates(self.session, extra_filters)
                pool = [*pool, *extra]

        query_tokens = set(tokenize(request.query)) if request.query else set()
        hits: list[SearchHit] = []
        for candidate in pool:
            keyword_score = self._keyword_score(candidate, query_tokens)
            graph_score = graph_scores.get(candidate.id, 0.0)
            semantic_score = semantic_scores.get(candidate.id, 0.0)
            combined = (
                weights["graph"] * graph_score
                + weights["semantic"] * min(1.0, semantic_score / 0.75)
                + weights["keyword"] * keyword_score
            )
            if request.query and combined <= 0 and request.mode != "keyword":
                continue

            matched, missing, related = self._skill_breakdown(
                candidate, requested_skills, matched_skill_ids.get(candidate.id, set())
            )
            hits.append(
                SearchHit(
                    candidate_id=candidate.id,
                    candidate_uuid=candidate.uuid,
                    full_name=candidate.full_name,
                    email=candidate.email,
                    current_title=candidate.current_title,
                    current_company=candidate.current_company_name,
                    location=", ".join(part for part in [candidate.city, candidate.country] if part) or None,
                    total_experience_years=candidate.total_experience_years or 0.0,
                    status=candidate.status,
                    highest_degree=candidate.highest_degree,
                    ai_score=round(combined * 100, 2),
                    keyword_score=round(keyword_score * 100, 2),
                    semantic_score=round(min(1.0, semantic_score / 0.75) * 100, 2),
                    graph_score=round(graph_score * 100, 2),
                    matched_skills=matched,
                    missing_skills=missing,
                    related_skills=related,
                    snippet=truncate(snippets.get(candidate.id) or candidate.ai_summary or "", 240) or None,
                    channels=sorted(channels.get(candidate.id, set())) or (["keyword"] if keyword_score else []),
                    top_skills=[link.display_name for link in candidate.skills[:8]],
                )
            )

        hits = self._sort(hits, request)
        total = len(hits)
        start = (request.page - 1) * request.page_size
        page_items = hits[start : start + request.page_size]

        answer = None
        answer_backend = None
        if request.include_answer and page_items:
            contexts = []
            for hit in page_items[:5]:
                hit_candidate = self.session.get(Candidate, hit.candidate_id)
                if hit_candidate is None:
                    continue
                contexts.append(
                    f"Candidate: {hit_candidate.full_name}\n"
                    f"Role: {hit_candidate.current_title or 'unknown'} at "
                    f"{hit_candidate.current_company_name or 'unknown'}\n"
                    f"Experience: {hit_candidate.total_experience_years} years\n"
                    f"Matched skills: {', '.join(item.skill for item in hit.matched_skills) or 'none'}\n"
                    f"Missing skills: {', '.join(hit.missing_skills) or 'none'}\n"
                    f"Score: {hit.ai_score}%"
                )
            answer, answer_backend = answer_with_context(request.query, contexts)

        return SearchResponse(
            query=request.query,
            mode=request.mode,
            interpreted_skills=requested_skills,
            interpreted_experience=min_experience,
            unknown_terms=parsed.unknown_terms,
            expanded_skills=expanded_view[:30],
            total=total,
            page=request.page,
            page_size=request.page_size,
            duration_ms=int((time.perf_counter() - started) * 1000),
            items=page_items,
            answer=answer,
            answer_backend=answer_backend,
            graph_paths=graph_paths,
            generated_at=datetime.now(UTC),
        )

    # -------------------------------------------------------------------- helpers
    def _keyword_score(self, candidate: Candidate, query_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        haystack = " ".join(
            filter(
                None,
                [
                    candidate.full_name,
                    candidate.current_title,
                    candidate.current_company_name,
                    candidate.headline,
                    candidate.city,
                    candidate.country,
                    candidate.highest_degree,
                    " ".join(link.display_name for link in candidate.skills),
                ],
            )
        )
        tokens = set(tokenize(haystack))
        if not tokens:
            return 0.0
        overlap = len(query_tokens & tokens)
        return round(overlap / len(query_tokens), 4)

    def _skill_breakdown(
        self, candidate: Candidate, requested: list[str], matched_ids: set[int]
    ) -> tuple[list[MatchedSkillHit], list[str], list[str]]:
        if not requested:
            return [], [], []
        candidate_skill_ids = {link.skill_id for link in candidate.skills if link.skill_id}
        candidate_keys = {link.normalized_name for link in candidate.skills}

        matched: list[MatchedSkillHit] = []
        missing: list[str] = []
        related: list[str] = []

        for name in requested:
            resolved = self.rag.taxonomy.resolve(name)
            if resolved and resolved.skill.id in candidate_skill_ids:
                matched.append(MatchedSkillHit(skill=resolved.skill.name, match_type="direct", score=1.0))
                continue
            if normalize_key(name) in candidate_keys:
                matched.append(MatchedSkillHit(skill=name, match_type="direct", score=1.0))
                continue
            if resolved:
                equivalents = self.rag.taxonomy.equivalent_ids(resolved.skill.id) & candidate_skill_ids
                if equivalents:
                    bridge = self.rag.taxonomy.get(next(iter(equivalents)))
                    matched.append(
                        MatchedSkillHit(
                            skill=resolved.skill.name,
                            match_type="related",
                            score=0.6,
                        )
                    )
                    if bridge:
                        related.append(f"{bridge.name} -> {resolved.skill.name}")
                    continue
                if resolved.skill.id in matched_ids:
                    matched.append(MatchedSkillHit(skill=resolved.skill.name, match_type="graph", score=0.5))
                    continue
            missing.append(resolved.skill.name if resolved else name)
        return matched, missing, related

    def _sort(self, hits: list[SearchHit], request: SearchRequest) -> list[SearchHit]:
        reverse = request.sort_dir == "desc"
        key_map = {
            "ai_score": lambda hit: hit.ai_score,
            "experience": lambda hit: hit.total_experience_years,
            "name": lambda hit: hit.full_name.lower(),
            "upload_date": lambda hit: hit.candidate_id,
        }
        key = key_map.get(request.sort_by, key_map["ai_score"])
        return sorted(hits, key=key, reverse=reverse)

    def suggest(self, prefix: str, *, limit: int = 8) -> SuggestResponse:
        prefix = (prefix or "").strip()
        if len(prefix) < 2:
            return SuggestResponse()

        lowered = prefix.lower()
        skills = [
            node.name
            for node in self.rag.taxonomy.all_skills()
            if node.name.lower().startswith(lowered) or any(s.lower().startswith(lowered) for s in node.synonyms)
        ][:limit]

        companies = [name for name, _ in repo.top_companies(self.session, limit=50) if lowered in (name or "").lower()][
            :limit
        ]
        filters = CandidateFilters(search=prefix, page=1, page_size=limit)
        candidates, _ = repo.list_candidates(self.session, filters)
        titles = list(
            dict.fromkeys(
                candidate.current_title
                for candidate in candidates
                if candidate.current_title and lowered in candidate.current_title.lower()
            )
        )[:limit]

        return SuggestResponse(
            skills=skills,
            companies=companies,
            titles=titles,
            candidates=[
                {
                    "id": candidate.id,
                    "uuid": candidate.uuid,
                    "full_name": candidate.full_name,
                    "current_title": candidate.current_title,
                }
                for candidate in candidates[:limit]
            ],
        )
