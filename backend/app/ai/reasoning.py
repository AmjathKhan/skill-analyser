"""Explainable-AI narrative generation.

Every explanation is derived from the structured match evidence, so the platform
is explainable by construction. When an LLM backend is configured the same
evidence is handed to the model as grounding context (Graph RAG step 5) and the
deterministic narrative is used as the fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.llm import get_llm
from app.core.constants import Recommendation
from app.core.logging import get_logger
from app.schemas.matching import CandidateMatch, MatchCriteria
from app.services.taxonomy import SkillTaxonomy

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert technical recruiter assistant inside an HR platform. "
    "You explain why a candidate matches a role using ONLY the supplied context. "
    "Never invent skills, employers or credentials. Be concise, factual and neutral."
)

#: Question templates keyed by skill category, used for interview suggestions.
QUESTION_BANK: dict[str, list[str]] = {
    "Programming Language": [
        "Describe a non-trivial problem you solved with {skill} and the trade-offs you made.",
        "How do you structure and test a large {skill} codebase?",
    ],
    "Frontend Framework": [
        "How do you manage state and re-render performance in {skill} applications?",
        "Walk through how you would structure a large {skill} app for a team of five engineers.",
    ],
    "Backend Framework": [
        "How do you design and version REST APIs in {skill}?",
        "Describe how you handle authentication, validation and background work in {skill}.",
    ],
    "Database": [
        "How do you diagnose and fix a slow query in {skill}?",
        "Describe your approach to schema design and indexing in {skill}.",
    ],
    "Graph Database": [
        "How would you model a recruitment knowledge graph in {skill}?",
        "Which traversal patterns in {skill} have you tuned for performance?",
    ],
    "DevOps": [
        "Walk me through a production deployment you automated with {skill}.",
        "How do you handle rollbacks and zero-downtime releases with {skill}?",
    ],
    "Cloud": [
        "Which {skill} services have you run in production, and how did you control cost?",
        "How do you design for failure and least privilege on {skill}?",
    ],
    "AI Discipline": [
        "Describe a {skill} project you shipped: data, evaluation and the outcome.",
        "How do you measure quality and guard against regressions in {skill} systems?",
    ],
    "ML Framework": [
        "How have you used {skill} beyond training - serving, monitoring, optimisation?",
        "Describe a debugging session on a {skill} model that was not converging.",
    ],
    "Testing": [
        "What is your testing strategy with {skill} and how do you keep suites fast?",
        "How do you decide what deserves a test in {skill}?",
    ],
    "Security": [
        "How have you applied {skill} to protect a production system?",
        "Describe a security review where {skill} changed your design.",
    ],
    "Soft Skill": [
        "Give an example where your {skill} changed the outcome of a project.",
        "How do you apply {skill} when the team disagrees with you?",
    ],
}

GENERIC_QUESTIONS = [
    "Walk me through your most impactful project in the last two years and your specific contribution.",
    "Describe a production incident you owned end to end: detection, mitigation and prevention.",
    "How do you decide between shipping fast and investing in engineering quality?",
]


@dataclass(slots=True)
class Narrative:
    explanation: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    interview_questions: list[str] = field(default_factory=list)
    learning_recommendations: list[str] = field(default_factory=list)
    career_fit: str | None = None
    generated_by: str = "template"


def _percent(value: float) -> str:
    return f"{round(value)}%"


def _score_label(score: float) -> str:
    if score >= 85:
        return "an excellent fit"
    if score >= 70:
        return "a strong fit"
    if score >= 50:
        return "a partial fit"
    return "a weak fit"


def build_template_narrative(
    match: CandidateMatch,
    criteria: MatchCriteria,
    taxonomy: SkillTaxonomy | None = None,
) -> Narrative:
    matched = [evidence.requested for evidence in match.matched_skills]
    related = [f"{evidence.matched_skill} (for {evidence.requested})" for evidence in match.related_skills]
    missing = [evidence.requested for evidence in match.missing_skills]
    mandatory_missing = [evidence.requested for evidence in match.missing_skills if evidence.mandatory]

    role = criteria.job_title or "the requested role"
    sentences: list[str] = [
        f"{match.full_name} scores {_percent(match.overall_score)} for {role}, "
        f"which makes this {_score_label(match.overall_score)}."
    ]
    if matched:
        sentences.append(
            f"Direct skill coverage is {_percent(match.breakdown.skill_score)}: "
            f"{', '.join(matched[:8])} are evidenced in the resume."
        )
    else:
        sentences.append("None of the required skills were found directly in the resume.")

    if related:
        sentences.append(
            "The knowledge graph also credits transferable skills: " + "; ".join(related[:5]) + "."
        )

    experience_note = (
        f"{match.total_experience_years} years of experience against a minimum of "
        f"{criteria.min_experience_years} years scores {_percent(match.breakdown.experience_score)}"
    )
    sentences.append(experience_note + ".")

    if criteria.preferred_certifications:
        sentences.append(
            f"Certification alignment scores {_percent(match.breakdown.certification_score)} "
            f"against the preferred credentials."
        )
    if match.breakdown.project_score:
        sentences.append(
            f"Project relevance scores {_percent(match.breakdown.project_score)} based on the technologies "
            "referenced in their project and experience descriptions."
        )
    if missing:
        sentences.append("Gaps to probe: " + ", ".join(missing[:6]) + ".")
    if mandatory_missing:
        sentences.append(
            "Note that " + ", ".join(mandatory_missing) + " was marked mandatory and is not evidenced, "
            "which caps the overall score."
        )
    sentences.append(f"Confidence in this assessment is {_percent(match.confidence)}, "
                     "reflecting resume completeness and the strength of the retrieval evidence.")

    strengths: list[str] = []
    for evidence in match.matched_skills[:6]:
        detail = f"{evidence.matched_skill or evidence.requested}"
        if evidence.years_experience:
            detail += f" ({evidence.years_experience} yrs)"
        elif evidence.proficiency:
            detail += f" ({evidence.proficiency})"
        strengths.append(detail)
    if match.total_experience_years >= criteria.min_experience_years and criteria.min_experience_years:
        strengths.append(f"Meets the experience bar ({match.total_experience_years} yrs)")
    if match.graph_context.certifications:
        strengths.append("Holds " + ", ".join(match.graph_context.certifications[:3]))

    gaps = [f"No evidence of {name}" for name in missing[:6]]
    if criteria.min_experience_years and match.total_experience_years < criteria.min_experience_years:
        gaps.append(
            f"Experience is {round(criteria.min_experience_years - match.total_experience_years, 1)} years short"
        )

    questions = build_interview_questions(match, criteria, taxonomy)
    learning = build_learning_recommendations(match, taxonomy)
    career_fit = build_career_fit(match, criteria)

    return Narrative(
        explanation=" ".join(sentences),
        strengths=list(dict.fromkeys(strengths))[:8],
        gaps=list(dict.fromkeys(gaps))[:8],
        interview_questions=questions,
        learning_recommendations=learning,
        career_fit=career_fit,
        generated_by="template",
    )


def build_interview_questions(
    match: CandidateMatch, criteria: MatchCriteria, taxonomy: SkillTaxonomy | None
) -> list[str]:
    questions: list[str] = []
    for evidence in match.matched_skills[:4]:
        skill_name = evidence.matched_skill or evidence.requested
        category = None
        if taxonomy is not None:
            node = taxonomy.by_name(skill_name)
            category = node.category if node else None
        templates = QUESTION_BANK.get(category or "", [])
        if not templates:
            templates = [
                "Describe a project where {skill} was central to the outcome, and what you would do differently now."
            ]
        questions.append(templates[len(questions) % len(templates)].format(skill=skill_name))

    for evidence in match.missing_skills[:2]:
        questions.append(
            f"We use {evidence.requested} heavily. How would you ramp up on it, and what adjacent "
            "experience would transfer?"
        )
    for evidence in match.related_skills[:2]:
        questions.append(
            f"You have {evidence.matched_skill}; how does that experience translate to {evidence.requested}?"
        )
    if match.total_experience_years and criteria.min_experience_years:
        questions.append(
            f"Across your {match.total_experience_years} years, which project best demonstrates "
            f"readiness for {criteria.job_title or 'this role'}?"
        )
    questions.extend(GENERIC_QUESTIONS)
    return list(dict.fromkeys(questions))[:8]


def build_learning_recommendations(match: CandidateMatch, taxonomy: SkillTaxonomy | None) -> list[str]:
    recommendations: list[str] = []
    for evidence in match.missing_skills[:5]:
        bridge: str | None = None
        if taxonomy is not None:
            node = taxonomy.by_name(evidence.requested)
            if node:
                candidate_skills = {name.lower() for name in match.graph_context.connected_skills}
                for expanded in taxonomy.expand(node.id, depth=1):
                    if expanded.skill.name.lower() in candidate_skills:
                        bridge = expanded.skill.name
                        break
        if bridge:
            recommendations.append(
                f"{evidence.requested}: build on existing {bridge} experience with a focused hands-on project."
            )
        else:
            recommendations.append(
                f"{evidence.requested}: start with the fundamentals and a small end-to-end project to build evidence."
            )
    if not recommendations and match.matched_skills:
        deepest = match.matched_skills[0]
        recommendations.append(
            f"Skills are well covered; deepen {deepest.matched_skill or deepest.requested} towards "
            "architecture-level ownership."
        )
    return recommendations[:6]


def build_career_fit(match: CandidateMatch, criteria: MatchCriteria) -> str:
    roles = match.graph_context.job_roles[:3]
    role_text = f" The knowledge graph associates their skill set with {', '.join(roles)}." if roles else ""
    if match.overall_score >= 85:
        return (
            f"Strong immediate fit for {criteria.job_title or 'the role'} with no material ramp-up expected."
            + role_text
        )
    if match.overall_score >= 70:
        return (
            f"Good fit for {criteria.job_title or 'the role'}; expect a short ramp-up on "
            f"{', '.join(evidence.requested for evidence in match.missing_skills[:2]) or 'team-specific tooling'}."
            + role_text
        )
    if match.overall_score >= 50:
        return (
            "Partial fit - suitable for an adjacent or more junior scope, or if the team can invest in ramp-up."
            + role_text
        )
    return "Not aligned with this requirement; consider for different openings." + role_text


def _parse_llm_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "explanation"
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(
            r"^(?:#+\s*)?(explanation|why|summary|strengths|gaps|risks|interview questions|questions|"
            r"learning recommendations|recommendations|career fit)\s*:?\s*$",
            stripped,
            re.IGNORECASE,
        )
        if heading:
            current = heading.group(1).lower()
            continue
        sections.setdefault(current, []).append(re.sub(r"^[-*\d.)\s]+", "", stripped))
    return sections


def generate_narrative(
    match: CandidateMatch,
    criteria: MatchCriteria,
    context_text: str,
    taxonomy: SkillTaxonomy | None = None,
) -> Narrative:
    """Deterministic narrative, optionally refined by the configured LLM."""
    narrative = build_template_narrative(match, criteria, taxonomy)

    llm = get_llm()
    if not llm.available():
        return narrative

    prompt = f"""Explain this candidate-to-role match for a recruiter.

CONTEXT (the only facts you may use):
{context_text}

SCORES:
- Overall: {round(match.overall_score)}%
- Skill: {round(match.breakdown.skill_score)}%
- Semantic: {round(match.breakdown.semantic_score)}%
- Experience: {round(match.breakdown.experience_score)}%
- Certifications: {round(match.breakdown.certification_score)}%
- Projects: {round(match.breakdown.project_score)}%
- Confidence: {round(match.confidence)}%
- Recommendation: {match.recommendation}

Respond with these sections exactly:
Explanation:
<2-4 sentences on why this score, naming the specific skills that drove it>
Strengths:
<up to 4 bullets>
Gaps:
<up to 4 bullets>
Interview Questions:
<up to 5 bullets tailored to the matched and missing skills>
Learning Recommendations:
<up to 4 bullets>
Career Fit:
<1-2 sentences>"""

    generated = llm.complete(system=SYSTEM_PROMPT, prompt=prompt)
    if not generated:
        return narrative

    sections = _parse_llm_sections(generated)
    explanation = " ".join(sections.get("explanation") or sections.get("why") or sections.get("summary") or [])
    return Narrative(
        explanation=explanation or narrative.explanation,
        strengths=(sections.get("strengths") or narrative.strengths)[:8],
        gaps=(sections.get("gaps") or sections.get("risks") or narrative.gaps)[:8],
        interview_questions=(
            sections.get("interview questions") or sections.get("questions") or narrative.interview_questions
        )[:8],
        learning_recommendations=(
            sections.get("learning recommendations") or sections.get("recommendations") or narrative.learning_recommendations
        )[:6],
        career_fit=" ".join(sections.get("career fit") or []) or narrative.career_fit,
        generated_by=llm.backend,
    )


def summarize_candidate(
    *,
    full_name: str,
    current_title: str | None,
    current_company: str | None,
    experience_years: float,
    top_skills: list[str],
    education: str | None,
    certifications: list[str],
    project_count: int,
    resume_excerpt: str | None = None,
) -> str:
    """Resume summarization: template first, LLM refinement when configured."""
    role = current_title or "Professional"
    company = f" at {current_company}" if current_company else ""
    skills_text = ", ".join(top_skills[:8]) or "no clearly extracted technical skills"
    parts = [
        f"{full_name} is a {role}{company} with {experience_years} years of experience.",
        f"Core skills include {skills_text}.",
    ]
    if education:
        parts.append(f"Holds a {education}.")
    if certifications:
        parts.append(f"Certified in {', '.join(certifications[:4])}.")
    if project_count:
        parts.append(f"{project_count} project(s) documented in the resume.")
    template_summary = " ".join(parts)

    llm = get_llm()
    if not llm.available():
        return template_summary

    prompt = (
        "Write a neutral 3-sentence recruiter-facing summary using only these facts.\n\n"
        f"Name: {full_name}\nRole: {role}{company}\nExperience: {experience_years} years\n"
        f"Skills: {skills_text}\nEducation: {education or 'not stated'}\n"
        f"Certifications: {', '.join(certifications[:6]) or 'none'}\nProjects: {project_count}\n"
        f"Resume excerpt: {(resume_excerpt or '')[:1500]}"
    )
    generated = llm.complete(system=SYSTEM_PROMPT, prompt=prompt, max_tokens=300)
    return generated or template_summary


def answer_with_context(question: str, context_blocks: list[str], *, fallback: str | None = None) -> tuple[str, str]:
    """Answer a recruiter question grounded in retrieved context. Returns (answer, backend)."""
    llm = get_llm()
    if not llm.available() or not context_blocks:
        return (fallback or _template_answer(question, context_blocks), "template")

    prompt = (
        f"Recruiter question: {question}\n\n"
        "Retrieved context (candidates ranked by relevance):\n"
        + "\n\n---\n\n".join(context_blocks[:8])
        + "\n\nAnswer in at most 6 sentences. Reference candidates by name. "
        "If the context is insufficient, say so explicitly."
    )
    generated = llm.complete(system=SYSTEM_PROMPT, prompt=prompt)
    if generated:
        return generated, llm.backend
    return (fallback or _template_answer(question, context_blocks), "template")


def _template_answer(question: str, context_blocks: list[str]) -> str:
    if not context_blocks:
        return (
            "No candidates in the knowledge graph match that query yet. Upload resumes or relax the "
            "filters and try again."
        )
    names: list[str] = []
    for block in context_blocks[:5]:
        first_line = block.split("\n", 1)[0]
        names.append(first_line.replace("Candidate:", "").strip())
    return (
        f"Based on graph and vector retrieval, the strongest candidates for \"{question}\" are "
        + ", ".join(names)
        + ". The scoring breakdown for each candidate lists the exact matched, related and missing skills "
        "that produced their ranking."
    )


def recommendation_for(score: float, *, mandatory_missing: bool = False) -> Recommendation:
    if mandatory_missing:
        return Recommendation.CONSIDER if score >= 60 else Recommendation.NOT_RECOMMENDED
    if score >= 85:
        return Recommendation.HIGHLY_RECOMMENDED
    if score >= 70:
        return Recommendation.RECOMMENDED
    if score >= 50:
        return Recommendation.CONSIDER
    return Recommendation.NOT_RECOMMENDED
