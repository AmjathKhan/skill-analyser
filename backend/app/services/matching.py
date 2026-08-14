"""AI skill matching engine.

Produces an explainable score per candidate from five weighted signals:

* **skill**         - direct taxonomy matches plus graph-inferred equivalents
* **semantic**      - vector similarity between the requirement and the resume
* **experience**    - years of experience vs. the requested minimum
* **certification** - preferred credentials actually held
* **project**       - required skills evidenced in projects/experience text

Signals that do not apply to a query (e.g. no certifications requested) are
marked not-applicable and their weight is redistributed, so scores stay
comparable and every number can be traced back to evidence.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.embeddings import cosine_similarity, get_embedder
from app.ai.graph_rag import GraphRAGEngine, Retrieval
from app.ai.reasoning import generate_narrative, recommendation_for
from app.ai.text_utils import normalize_key, similarity, truncate
from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai import MatchResult, MatchRun
from app.models.candidate import Candidate, CandidateSkill
from app.schemas.matching import (
    CandidateMatch,
    MatchBreakdown,
    MatchCriteria,
    MatchResponse,
    ScoreComponent,
    SkillEvidence,
    SkillGapItem,
)
from app.services.taxonomy import SkillNode, get_taxonomy

logger = get_logger(__name__)

SEMANTIC_SKILL_THRESHOLD = 0.72
#: Cosine value that is treated as a perfect semantic match (calibration).
SEMANTIC_FULL_SCORE_AT = 0.75
PREFERRED_SKILL_WEIGHT = 0.5
MANDATORY_MISS_PENALTY = 0.6

RELATION_CREDIT = {
    "PARENT_OF": 0.75,
    "RELATED_TO": 0.6,
    "DEPENDS_ON": 0.65,
}


@dataclass(slots=True)
class RequestedSkill:
    raw: str
    node: SkillNode | None
    weight: float
    mandatory: bool

    @property
    def display(self) -> str:
        return self.node.name if self.node else self.raw


class MatchingEngine:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.taxonomy = get_taxonomy(session)
        self.rag = GraphRAGEngine(session)
        self.embedder = get_embedder()
        self._vector_cache: dict[str, np.ndarray] = {}

    # ---------------------------------------------------------------------- run
    def run(self, criteria: MatchCriteria, *, user_id: int | None = None) -> MatchResponse:
        started = time.perf_counter()
        requested = self._prepare_requested(criteria)

        retrieval = self.rag.retrieve(
            skills=[item.display for item in requested],
            query_text=criteria.job_description or " ".join(item.display for item in requested),
            min_experience_years=criteria.min_experience_years or None,
            preferred_certifications=criteria.preferred_certifications,
            preferred_domain=criteria.preferred_domain,
            job_title=criteria.job_title,
            job_description=criteria.job_description,
            top_k=max(criteria.top_k * 4, 60),
            candidate_ids=criteria.candidate_ids,
        )

        candidate_ids = retrieval.candidate_ids()
        if len(candidate_ids) < criteria.top_k:
            candidate_ids = self._widen_candidate_pool(candidate_ids, criteria)

        candidates = self.rag.load_candidates(candidate_ids)
        if criteria.statuses:
            allowed = {status.lower() for status in criteria.statuses}
            candidates = [candidate for candidate in candidates if (candidate.status or "").lower() in allowed]

        self._warm_vector_cache(requested, candidates)

        matches: list[CandidateMatch] = []
        for candidate in candidates:
            match = self._score_candidate(candidate, criteria, requested, retrieval)
            if match.overall_score >= criteria.min_score:
                matches.append(match)

        matches.sort(key=lambda item: (-item.overall_score, -item.total_experience_years, item.full_name))
        matches = matches[: criteria.top_k]

        for index, match in enumerate(matches, start=1):
            match.rank = index

        if criteria.include_explanations:
            for match in matches:
                self._attach_explanation(match, criteria, retrieval)

        duration_ms = int((time.perf_counter() - started) * 1000)
        run_id = run_uuid = None
        if criteria.persist and matches:
            run = self._persist(criteria, matches, len(candidates), duration_ms, user_id)
            run_id, run_uuid = run.id, run.uuid

        return MatchResponse(
            run_id=run_id,
            run_uuid=run_uuid,
            criteria=criteria,
            total_candidates_evaluated=len(candidates),
            returned=len(matches),
            duration_ms=duration_ms,
            generated_at=datetime.now(UTC),
            embedding_model=self.embedder.model_name,
            graph_backend=self.rag.graph.name,
            vector_backend=settings.vector_backend.value,
            llm_backend=settings.llm_backend.value,
            results=matches,
        )

    def score_single(
        self, candidate_id: int, criteria: MatchCriteria, *, include_explanation: bool = True
    ) -> CandidateMatch | None:
        """Score one candidate - used by the candidate profile AI score panel."""
        scoped = criteria.model_copy(update={"candidate_ids": [candidate_id], "top_k": 1, "persist": False,
                                             "min_score": 0.0, "include_explanations": include_explanation})
        response = self.run(scoped)
        return response.results[0] if response.results else None

    # ------------------------------------------------------------------ scoring
    def _prepare_requested(self, criteria: MatchCriteria) -> list[RequestedSkill]:
        mandatory_keys = {normalize_key(name) for name in criteria.mandatory_skills}
        requested: list[RequestedSkill] = []
        seen: set[str] = set()

        for raw in criteria.required_skills:
            key = normalize_key(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            match = self.taxonomy.resolve(raw)
            requested.append(
                RequestedSkill(raw=raw, node=match.skill if match else None, weight=1.0, mandatory=key in mandatory_keys)
            )
        for raw in criteria.preferred_skills:
            key = normalize_key(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            match = self.taxonomy.resolve(raw)
            requested.append(
                RequestedSkill(
                    raw=raw, node=match.skill if match else None, weight=PREFERRED_SKILL_WEIGHT, mandatory=False
                )
            )
        return requested

    def _widen_candidate_pool(self, existing: list[int], criteria: MatchCriteria) -> list[int]:
        """Retrieval may return few candidates (cold graph); top up with recent profiles."""
        statement = (
            select(Candidate.id)
            .where(Candidate.is_deleted.is_(False))
            .order_by(Candidate.created_at.desc())
            .limit(max(criteria.top_k * 5, 50))
        )
        if criteria.candidate_ids:
            statement = statement.where(Candidate.id.in_(criteria.candidate_ids))
        if criteria.min_experience_years:
            statement = statement.where(
                Candidate.total_experience_years >= max(0.0, criteria.min_experience_years - 2)
            )
        extra = list(self.session.scalars(statement))
        return list(dict.fromkeys([*existing, *extra]))

    def _warm_vector_cache(self, requested: Sequence[RequestedSkill], candidates: Sequence[Candidate]) -> None:
        names: set[str] = {item.display for item in requested}
        for candidate in candidates:
            for link in candidate.skills:
                names.add(link.skill.name if link.skill else link.raw_text)
        pending = [name for name in names if name and name not in self._vector_cache]
        if not pending:
            return
        vectors = self.embedder.encode(pending)
        for name, vector in zip(pending, np.atleast_2d(vectors), strict=False):
            self._vector_cache[name] = vector

    def _skill_vector(self, name: str) -> np.ndarray:
        vector = self._vector_cache.get(name)
        if vector is None:
            vector = self.embedder.encode(name)
            self._vector_cache[name] = vector
        return vector

    def _score_candidate(
        self,
        candidate: Candidate,
        criteria: MatchCriteria,
        requested: Sequence[RequestedSkill],
        retrieval: Retrieval,
    ) -> CandidateMatch:
        by_skill_id: dict[int, CandidateSkill] = {}
        by_key: dict[str, CandidateSkill] = {}
        for link in candidate.skills:
            if link.skill_id:
                by_skill_id[link.skill_id] = link
            by_key[link.normalized_name or normalize_key(link.raw_text)] = link

        matched: list[SkillEvidence] = []
        related: list[SkillEvidence] = []
        missing: list[SkillEvidence] = []
        skill_numerator = 0.0
        skill_denominator = 0.0
        mandatory_missing = False

        for item in requested:
            evidence = self._evaluate_skill(item, candidate, by_skill_id, by_key)
            skill_denominator += item.weight
            skill_numerator += item.weight * evidence.score
            if evidence.match_type in {"exact", "synonym", "fuzzy"}:
                matched.append(evidence)
            elif evidence.match_type == "missing":
                missing.append(evidence)
                if item.mandatory:
                    mandatory_missing = True
            else:
                related.append(evidence)

        skill_score = round(100 * skill_numerator / skill_denominator, 2) if skill_denominator else 0.0

        retrieval_entry = retrieval.candidates.get(candidate.id)
        vector_score = retrieval_entry.vector_score if retrieval_entry else 0.0
        semantic_score = round(100 * min(1.0, max(0.0, vector_score) / SEMANTIC_FULL_SCORE_AT), 2)
        has_embeddings = retrieval_entry is not None and "vector" in retrieval_entry.channels

        experience_score, experience_detail, experience_applicable = self._experience_score(candidate, criteria)
        certification_score, certification_detail, certification_applicable, _matched_certs = (
            self._certification_score(candidate, criteria)
        )
        project_score, project_detail, project_applicable = self._project_score(candidate, requested)

        weights = self._weights(criteria)
        components = [
            ScoreComponent(
                name="skill",
                score=skill_score,
                weight=weights["skill"],
                contribution=0.0,
                detail=f"{len(matched)} direct, {len(related)} related, {len(missing)} missing of {len(requested)} requested skills",
            ),
            ScoreComponent(
                name="semantic",
                score=semantic_score if has_embeddings else 0.0,
                weight=weights["semantic"] if has_embeddings else 0.0,
                contribution=0.0,
                detail=(
                    f"resume/requirement cosine {round(vector_score, 3)} via {settings.vector_backend.value}"
                    if has_embeddings
                    else "no resume embedding available yet"
                ),
            ),
            ScoreComponent(
                name="experience",
                score=experience_score,
                weight=weights["experience"] if experience_applicable else 0.0,
                contribution=0.0,
                detail=experience_detail,
            ),
            ScoreComponent(
                name="certification",
                score=certification_score,
                weight=weights["certification"] if certification_applicable else 0.0,
                contribution=0.0,
                detail=certification_detail,
            ),
            ScoreComponent(
                name="project",
                score=project_score,
                weight=weights["project"] if project_applicable else 0.0,
                contribution=0.0,
                detail=project_detail,
            ),
        ]

        active_weight = sum(component.weight for component in components) or 1.0
        overall = 0.0
        for component in components:
            normalized_weight = component.weight / active_weight
            component.contribution = round(normalized_weight * component.score, 2)
            component.weight = round(normalized_weight, 4)
            overall += component.contribution

        if mandatory_missing:
            overall *= MANDATORY_MISS_PENALTY
        overall = round(min(100.0, max(0.0, overall)), 2)

        confidence = self._confidence(candidate, matched, retrieval_entry, len(requested))
        recommendation = recommendation_for(overall, mandatory_missing=mandatory_missing)

        additional = [
            (link.skill.name if link.skill else link.raw_text)
            for link in sorted(candidate.skills, key=lambda link: -(link.confidence or 0))
            if (link.skill.name if link.skill else link.raw_text)
            not in {evidence.matched_skill for evidence in [*matched, *related]}
        ][:15]

        return CandidateMatch(
            candidate_id=candidate.id,
            candidate_uuid=candidate.uuid,
            full_name=candidate.full_name,
            email=candidate.email,
            current_title=candidate.current_title,
            current_company=candidate.current_company_name,
            location=", ".join(part for part in [candidate.city, candidate.country] if part) or None,
            total_experience_years=candidate.total_experience_years,
            highest_degree=candidate.highest_degree,
            status=candidate.status,
            overall_score=overall,
            confidence=confidence,
            recommendation=recommendation.value,
            breakdown=MatchBreakdown(
                skill_score=skill_score,
                semantic_score=semantic_score,
                experience_score=experience_score,
                certification_score=certification_score,
                project_score=project_score,
                components=components,
                weights={component.name: component.weight for component in components},
            ),
            matched_skills=matched,
            related_skills=related,
            missing_skills=missing,
            additional_skills=additional,
        )

    def _evaluate_skill(
        self,
        item: RequestedSkill,
        candidate: Candidate,
        by_skill_id: dict[int, CandidateSkill],
        by_key: dict[str, CandidateSkill],
    ) -> SkillEvidence:
        # 1. Direct taxonomy hit.
        link: CandidateSkill | None = None
        if item.node is not None:
            link = by_skill_id.get(item.node.id)
        if link is None:
            link = by_key.get(normalize_key(item.raw))

        if link is not None:
            match_type = "exact"
            if item.node and link.skill_id == item.node.id and normalize_key(link.raw_text) != item.node.normalized:
                match_type = "synonym"
            return SkillEvidence(
                requested=item.display,
                matched_skill=link.skill.name if link.skill else link.raw_text,
                match_type=match_type,
                score=1.0,
                confidence=float(link.confidence or 0.8),
                proficiency=link.proficiency,
                years_experience=link.years_experience,
                source=link.source,
                evidence=truncate(link.evidence or "", 220) or None,
                mandatory=item.mandatory,
            )

        # 2. Graph-inferred equivalence (parent / child / related skills).
        if item.node is not None:
            best: tuple[float, CandidateSkill, str, str] | None = None
            for expanded in self.taxonomy.expand(item.node.id, depth=2):
                candidate_link = by_skill_id.get(expanded.skill.id)
                if candidate_link is None:
                    continue
                credit = RELATION_CREDIT.get(expanded.relation, 0.55) * expanded.weight
                if best is None or credit > best[0]:
                    best = (credit, candidate_link, expanded.relation, expanded.via or item.display)
            if best is not None:
                credit, candidate_link, relation, _via = best
                return SkillEvidence(
                    requested=item.display,
                    matched_skill=candidate_link.skill.name if candidate_link.skill else candidate_link.raw_text,
                    match_type="related",
                    score=round(min(0.85, credit), 3),
                    confidence=float(candidate_link.confidence or 0.7) * 0.9,
                    proficiency=candidate_link.proficiency,
                    years_experience=candidate_link.years_experience,
                    source="graph_inference",
                    evidence=truncate(candidate_link.evidence or "", 220) or None,
                    mandatory=item.mandatory,
                    graph_path=[candidate_link.skill.name if candidate_link.skill else candidate_link.raw_text,
                                relation, item.display],
                )

        # 3. Semantic fallback over the candidate's skill vocabulary.
        requested_vector = self._skill_vector(item.display)
        best_semantic: tuple[float, str] | None = None
        for link in candidate.skills:
            name = link.skill.name if link.skill else link.raw_text
            score = cosine_similarity(requested_vector, self._skill_vector(name))
            lexical = similarity(item.display, name)
            score = max(score, lexical * 0.9)
            if best_semantic is None or score > best_semantic[0]:
                best_semantic = (score, name)
        if best_semantic and best_semantic[0] >= SEMANTIC_SKILL_THRESHOLD:
            score, name = best_semantic
            return SkillEvidence(
                requested=item.display,
                matched_skill=name,
                match_type="semantic",
                score=round(min(0.8, score * 0.8), 3),
                confidence=round(score, 3),
                source="semantic_inference",
                mandatory=item.mandatory,
                evidence=f"Semantic similarity {round(score, 3)} to '{name}'",
            )

        return SkillEvidence(
            requested=item.display,
            matched_skill=None,
            match_type="missing",
            score=0.0,
            confidence=0.9,
            mandatory=item.mandatory,
            evidence="Not found in resume skills, projects or experience",
        )

    def _experience_score(self, candidate: Candidate, criteria: MatchCriteria) -> tuple[float, str, bool]:
        years = float(candidate.total_experience_years or 0.0)
        minimum = float(criteria.min_experience_years or 0.0)
        maximum = criteria.max_experience_years

        if minimum <= 0 and maximum is None:
            return (
                100.0 if years > 0 else 60.0,
                f"{years} years of experience (no minimum requested)",
                False,
            )

        if minimum and years >= minimum:
            score = 100.0
            detail = f"{years} years meets the {minimum} year minimum"
            if maximum and years > maximum:
                score = 88.0
                detail = f"{years} years exceeds the {maximum} year band (possible over-qualification)"
        elif minimum:
            ratio = years / minimum if minimum else 0.0
            score = round(max(0.0, min(1.0, ratio)) ** 1.2 * 100, 2)
            detail = f"{years} years against a {minimum} year minimum ({round(ratio * 100)}% of the bar)"
        else:
            score = 100.0 if (maximum is None or years <= maximum) else 85.0
            detail = f"{years} years within the requested band"
        return score, detail, True

    def _certification_score(
        self, candidate: Candidate, criteria: MatchCriteria
    ) -> tuple[float, str, bool, list[str]]:
        requested = criteria.preferred_certifications
        held = [certification.name for certification in candidate.certifications]
        if not requested:
            detail = f"{len(held)} certification(s) on file; none requested" if held else "no certifications requested"
            return (100.0 if held else 70.0), detail, False, held

        matched: list[str] = []
        for wanted in requested:
            wanted_key = normalize_key(wanted)
            for certification in candidate.certifications:
                held_key = certification.normalized_name or normalize_key(certification.name)
                if wanted_key and (wanted_key in held_key or held_key in wanted_key or similarity(wanted, certification.name) >= 0.85):
                    matched.append(certification.name)
                    break
        score = round(100 * len(matched) / len(requested), 2)
        detail = (
            f"{len(matched)}/{len(requested)} preferred certifications held"
            + (f": {', '.join(matched[:4])}" if matched else "")
        )
        return score, detail, True, matched

    def _project_score(self, candidate: Candidate, requested: Sequence[RequestedSkill]) -> tuple[float, str, bool]:
        blocks: list[str] = []
        for project in candidate.projects:
            blocks.append(
                " ".join(
                    filter(
                        None,
                        [project.name, project.role, project.description, " ".join(map(str, project.technologies or []))],
                    )
                )
            )
        for experience in candidate.experiences:
            blocks.append(
                " ".join(
                    filter(
                        None,
                        [
                            experience.job_title,
                            experience.description,
                            " ".join(map(str, experience.technologies or [])),
                        ],
                    )
                )
            )
        text = "\n".join(block for block in blocks if block.strip())
        if not text.strip() or not requested:
            return 0.0, "no project or experience descriptions available", False

        found = {match.skill.id for match in self.taxonomy.scan_text(text)}
        found_keys = {normalize_key(word) for word in text.split()}
        hits = 0
        hit_names: list[str] = []
        for item in requested:
            if item.node and item.node.id in found:
                hits += 1
                hit_names.append(item.node.name)
            elif normalize_key(item.raw) in found_keys:
                hits += 1
                hit_names.append(item.raw)
        score = round(100 * hits / len(requested), 2)
        detail = (
            f"{hits}/{len(requested)} requested skills appear in project/experience descriptions"
            + (f": {', '.join(hit_names[:5])}" if hit_names else "")
        )
        return score, detail, True

    def _weights(self, criteria: MatchCriteria) -> dict[str, float]:
        weights = dict(settings.match_weights)
        if criteria.weights:
            for key, value in criteria.weights.items():
                if key in weights and value is not None and value >= 0:
                    weights[key] = float(value)
        total = sum(weights.values()) or 1.0
        return {key: value / total for key, value in weights.items()}

    def _confidence(
        self,
        candidate: Candidate,
        matched: Sequence[SkillEvidence],
        retrieval_entry: object | None,
        requested_count: int,
    ) -> float:
        skill_confidence = (
            sum(evidence.confidence for evidence in matched) / len(matched) if matched else 0.55
        )
        completeness = candidate.profile_completeness
        if completeness is None:
            filled = sum(
                1
                for value in [
                    candidate.email,
                    candidate.phone,
                    candidate.current_title,
                    candidate.current_company_name,
                    candidate.highest_degree,
                    candidate.total_experience_years or None,
                    candidate.skills or None,
                    candidate.experiences or None,
                ]
                if value
            )
            completeness = filled / 8
        channels: set[str] = getattr(retrieval_entry, "channels", set()) or set()
        channel_factor = min(1.0, len(channels) / 2)
        coverage = (len(matched) / requested_count) if requested_count else 0.0

        raw = 0.30 + 0.25 * skill_confidence + 0.20 * float(completeness) + 0.15 * channel_factor + 0.10 * coverage
        return round(min(1.0, max(0.0, raw)) * 100, 1)

    # -------------------------------------------------------------- explanation
    def _attach_explanation(self, match: CandidateMatch, criteria: MatchCriteria, retrieval: Retrieval) -> None:
        candidate = self.session.get(Candidate, match.candidate_id)
        if candidate is None:
            return
        match.graph_context = self.rag.candidate_graph_context(
            match.candidate_id,
            requested_skills=[evidence.requested for evidence in [*match.matched_skills, *match.missing_skills]],
            include_similar=True,
        )
        entry = retrieval.candidates.get(match.candidate_id)
        context_text = self.rag.build_context_text(
            candidate=candidate,
            requested_skills=list(criteria.all_skills),
            matched=[evidence.requested for evidence in match.matched_skills],
            missing=[evidence.requested for evidence in match.missing_skills],
            related=[f"{evidence.matched_skill}->{evidence.requested}" for evidence in match.related_skills],
            graph_context=match.graph_context,
            snippets=getattr(entry, "snippets", []) or [],
        )
        narrative = generate_narrative(match, criteria, context_text, self.taxonomy)
        match.explanation = narrative.explanation
        match.strengths = narrative.strengths
        match.gaps = narrative.gaps
        match.interview_questions = narrative.interview_questions
        match.learning_recommendations = narrative.learning_recommendations
        match.career_fit = narrative.career_fit

    # ----------------------------------------------------------------- persist
    def _persist(
        self,
        criteria: MatchCriteria,
        matches: Sequence[CandidateMatch],
        evaluated: int,
        duration_ms: int,
        user_id: int | None,
    ) -> MatchRun:
        run = MatchRun(
            created_by_id=user_id,
            job_requirement_id=criteria.job_requirement_id,
            title=criteria.job_title or ", ".join(criteria.required_skills[:4]) or "Skill match",
            criteria=criteria.model_dump(mode="json"),
            weights=self._weights(criteria),
            candidates_evaluated=evaluated,
            top_score=matches[0].overall_score if matches else None,
            duration_ms=duration_ms,
            graph_backend=self.rag.graph.name,
            embedding_model=self.embedder.model_name,
        )
        self.session.add(run)
        self.session.flush()

        for match in matches:
            self.session.add(
                MatchResult(
                    match_run_id=run.id,
                    candidate_id=match.candidate_id,
                    rank=match.rank,
                    overall_score=match.overall_score,
                    skill_score=match.breakdown.skill_score,
                    semantic_score=match.breakdown.semantic_score,
                    experience_score=match.breakdown.experience_score,
                    certification_score=match.breakdown.certification_score,
                    project_score=match.breakdown.project_score,
                    confidence=match.confidence,
                    recommendation=match.recommendation,
                    matched_skills=[evidence.model_dump(mode="json") for evidence in match.matched_skills],
                    related_skills=[evidence.model_dump(mode="json") for evidence in match.related_skills],
                    missing_skills=[evidence.model_dump(mode="json") for evidence in match.missing_skills],
                    score_breakdown=match.breakdown.model_dump(mode="json"),
                    graph_context=match.graph_context.model_dump(mode="json"),
                    explanation=match.explanation,
                    interview_questions=match.interview_questions,
                    learning_recommendations=match.learning_recommendations,
                )
            )
            candidate = self.session.get(Candidate, match.candidate_id)
            if candidate is not None:
                candidate.last_match_score = match.overall_score
        self.session.flush()
        return run


def analyze_skill_gaps(
    session: Session, required_skills: Iterable[str], *, candidate_limit: int = 500
) -> list[SkillGapItem]:
    """Coverage of each requested skill across the candidate pool (for reports)."""
    taxonomy = get_taxonomy(session)
    total_candidates = (
        session.scalar(select(func.count(Candidate.id)).where(Candidate.is_deleted.is_(False))) or 0
    )
    items: list[SkillGapItem] = []
    for raw in required_skills:
        match = taxonomy.resolve(raw)
        name = match.skill.name if match else raw
        if match:
            count = (
                session.scalar(
                    select(func.count(func.distinct(CandidateSkill.candidate_id)))
                    .join(Candidate, Candidate.id == CandidateSkill.candidate_id)
                    .where(CandidateSkill.skill_id == match.skill.id, Candidate.is_deleted.is_(False))
                )
                or 0
            )
        else:
            count = (
                session.scalar(
                    select(func.count(func.distinct(CandidateSkill.candidate_id)))
                    .join(Candidate, Candidate.id == CandidateSkill.candidate_id)
                    .where(CandidateSkill.normalized_name == normalize_key(raw), Candidate.is_deleted.is_(False))
                )
                or 0
            )
        coverage = round(100 * count / total_candidates, 2) if total_candidates else 0.0
        suggestions: list[str] = []
        if match:
            suggestions = [expanded.skill.name for expanded in taxonomy.expand(match.skill.id, depth=1)[:4]]
        items.append(
            SkillGapItem(
                skill=name,
                category=match.skill.category if match else None,
                candidates_with_skill=count,
                coverage_percent=coverage,
                demand_score=round(100 - coverage, 2),
                suggested_learning=suggestions,
            )
        )
    items.sort(key=lambda item: item.coverage_percent)
    return items
