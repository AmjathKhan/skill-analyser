"""Asynchronous resume processing pipeline.

    upload -> text extraction -> entity extraction -> taxonomy normalization
          -> candidate persistence -> embedding generation -> graph sync

Each stage updates ``Resume.status`` so the UI can show live progress, and every
failure is captured on the row instead of losing the upload.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.document_parser import extract_document
from app.ai.embeddings import build_candidate_document, get_embedder
from app.ai.extractors import parse_resume_text
from app.ai.reasoning import summarize_candidate
from app.ai.text_utils import chunk_text, normalize_key, title_case, truncate
from app.ai.vector_store import VectorRecord, get_vector_store
from app.core.constants import (
    AuditAction,
    CandidateStatus,
    EmbeddingKind,
    ProficiencyLevel,
    ResumeStatus,
    SkillSource,
)
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.graph.builder import KnowledgeGraphBuilder
from app.models.candidate import (
    Candidate,
    CandidateSkill,
    Certification,
    Company,
    Education,
    Experience,
    Project,
)
from app.models.resume import Resume
from app.schemas.parsed import ParsedResume
from app.services import storage
from app.services.audit import record_audit
from app.services.taxonomy import get_taxonomy

logger = get_logger(__name__)

PROFICIENCY_HINTS = (
    (("expert", "expertise", "architect", "lead", "mastery"), ProficiencyLevel.EXPERT),
    (("advanced", "strong", "extensive", "senior"), ProficiencyLevel.ADVANCED),
    (("intermediate", "working knowledge", "hands-on", "proficient"), ProficiencyLevel.INTERMEDIATE),
    (("basic", "beginner", "familiar", "exposure", "learning"), ProficiencyLevel.BEGINNER),
)


@dataclass(slots=True)
class ProcessingResult:
    resume_id: int
    candidate_id: int | None = None
    status: str = ResumeStatus.COMPLETED.value
    skills_extracted: int = 0
    skills_normalized: int = 0
    experiences: int = 0
    educations: int = 0
    projects: int = 0
    certifications: int = 0
    embeddings: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    duration_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "skills_extracted": self.skills_extracted,
            "skills_normalized": self.skills_normalized,
            "experiences": self.experiences,
            "educations": self.educations,
            "projects": self.projects,
            "certifications": self.certifications,
            "embeddings": self.embeddings,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
            "duration_ms": self.duration_ms,
            "warnings": self.warnings,
            "error": self.error,
        }


# --------------------------------------------------------------------------- upload
def find_duplicate(session: Session, checksum: str) -> Resume | None:
    return session.scalar(
        select(Resume).where(Resume.checksum == checksum, Resume.status != ResumeStatus.DUPLICATE.value)
    )


def create_resume(
    session: Session,
    *,
    data: bytes,
    filename: str,
    uploaded_by_id: int | None,
    allow_duplicate: bool = False,
) -> tuple[Resume, Resume | None]:
    """Persist the upload. Returns ``(resume, duplicate_of)``."""
    checksum = storage.compute_checksum(data)
    duplicate = find_duplicate(session, checksum)
    if duplicate is not None and not allow_duplicate:
        resume = Resume(
            candidate_id=duplicate.candidate_id,
            uploaded_by_id=uploaded_by_id,
            original_filename=filename,
            stored_filename=duplicate.stored_filename,
            storage_path=duplicate.storage_path,
            content_type=duplicate.content_type,
            extension=duplicate.extension,
            file_size=len(data),
            checksum=checksum,
            is_encrypted=duplicate.is_encrypted,
            status=ResumeStatus.DUPLICATE.value,
            duplicate_of_id=duplicate.id,
            parse_error="Duplicate of an existing resume (identical file checksum)",
        )
        session.add(resume)
        session.flush()
        return resume, duplicate

    stored = storage.save_resume(data, filename)
    resume = Resume(
        uploaded_by_id=uploaded_by_id,
        original_filename=storage.sanitize_filename(filename),
        stored_filename=stored.stored_filename,
        storage_path=stored.relative_path,
        content_type=storage.CONTENT_TYPES.get(stored.extension),
        extension=stored.extension,
        file_size=stored.size,
        checksum=stored.checksum,
        is_encrypted=stored.encrypted,
        status=ResumeStatus.QUEUED.value,
    )
    session.add(resume)
    session.flush()
    return resume, None


# ------------------------------------------------------------------------ pipeline
def process_resume(session: Session, resume_id: int, *, actor_id: int | None = None) -> ProcessingResult:
    started = time.perf_counter()
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise NotFoundError(f"Resume {resume_id} not found")

    result = ProcessingResult(resume_id=resume.id)
    if resume.status == ResumeStatus.DUPLICATE.value:
        result.status = ResumeStatus.DUPLICATE.value
        result.candidate_id = resume.candidate_id
        return result

    resume.status = ResumeStatus.PARSING.value
    resume.parse_started_at = datetime.now(UTC)
    resume.parse_error = None
    session.flush()

    temp_path = None
    try:
        path, is_temp = storage.materialize_for_parsing(
            resume.storage_path, encrypted=resume.is_encrypted, extension=resume.extension
        )
        temp_path = path if is_temp else None
        document = extract_document(path)
        resume.raw_text = document.text
        resume.page_count = document.page_count
        resume.word_count = document.word_count
        resume.ocr_used = document.ocr_used
        resume.extraction_backend = document.backend
        result.warnings.extend(document.warnings)

        if document.is_empty:
            raise ValueError(
                "No readable text could be extracted. If this is a scanned resume, enable OCR (ENABLE_OCR=true)."
            )

        parsed = parse_resume_text(document.text)
        result.warnings.extend(parsed.warnings)
        resume.parsed_data = parsed.model_dump(mode="json")

        candidate = _upsert_candidate(session, parsed, resume)
        resume.candidate_id = candidate.id
        session.flush()

        _replace_experiences(session, candidate, parsed)
        _replace_educations(session, candidate, parsed)
        _replace_projects(session, candidate, parsed)
        _replace_certifications(session, candidate, parsed)
        extracted, normalized = _persist_skills(session, candidate, parsed, document.text)
        session.flush()
        # Children are inserted by foreign key, so the loaded collections are stale;
        # expire them before the summary, embedding and graph stages read them back.
        session.expire(candidate, ["skills", "experiences", "educations", "projects", "certifications"])

        result.experiences = len(parsed.experiences)
        result.educations = len(parsed.educations)
        result.projects = len(parsed.projects)
        result.certifications = len(parsed.certifications)
        result.skills_extracted = extracted
        result.skills_normalized = normalized

        candidate.profile_completeness = _completeness(candidate, parsed)
        candidate.ai_summary = summarize_candidate(
            full_name=candidate.full_name,
            current_title=candidate.current_title,
            current_company=candidate.current_company_name,
            experience_years=candidate.total_experience_years,
            top_skills=[link.display_name for link in candidate.skills[:10]],
            education=candidate.highest_degree,
            certifications=[certification.name for certification in candidate.certifications],
            project_count=len(candidate.projects),
            resume_excerpt=truncate(document.text, 1500),
        )
        candidate.ai_highlights = _highlights(candidate, parsed)
        session.flush()

        resume.status = ResumeStatus.EMBEDDING.value
        session.flush()
        result.embeddings = generate_candidate_embeddings(session, candidate, resume)

        resume.status = ResumeStatus.GRAPH_SYNC.value
        session.flush()
        builder = KnowledgeGraphBuilder(session)
        nodes, edges = builder.sync_candidate(candidate)
        result.graph_nodes, result.graph_edges = nodes, edges

        resume.status = ResumeStatus.COMPLETED.value
        resume.parse_completed_at = datetime.now(UTC)
        resume.parse_duration_ms = int((time.perf_counter() - started) * 1000)
        result.candidate_id = candidate.id
        result.status = resume.status
        result.duration_ms = resume.parse_duration_ms

        record_audit(
            session,
            action=AuditAction.RESUME_UPLOAD,
            user_id=actor_id or resume.uploaded_by_id,
            entity_type="resume",
            entity_id=resume.id,
            description=f"Processed resume '{resume.original_filename}' into candidate #{candidate.id}",
            meta=result.as_dict(),
        )
        logger.info(
            "resume %s processed in %sms (candidate=%s, skills=%s)",
            resume.id,
            result.duration_ms,
            candidate.id,
            result.skills_extracted,
        )
    except Exception as exc:
        session.rollback()
        resume = session.get(Resume, resume_id)
        if resume is not None:
            resume.status = ResumeStatus.FAILED.value
            resume.parse_error = f"{exc.__class__.__name__}: {exc}"[:2000]
            resume.parse_completed_at = datetime.now(UTC)
        result.status = ResumeStatus.FAILED.value
        result.error = str(exc)
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("resume %s processing failed", resume_id)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return result


# ------------------------------------------------------------------ persistence
def _upsert_candidate(session: Session, parsed: ParsedResume, resume: Resume) -> Candidate:
    personal = parsed.personal
    candidate: Candidate | None = None

    if resume.candidate_id:
        candidate = session.get(Candidate, resume.candidate_id)
    if candidate is None and personal.email:
        candidate = session.scalar(
            select(Candidate).where(
                Candidate.email == personal.email.lower(), Candidate.is_deleted.is_(False)
            )
        )
    if candidate is None and personal.phone:
        digits = "".join(character for character in personal.phone if character.isdigit())[-10:]
        if len(digits) >= 8:
            candidate = session.scalar(
                select(Candidate).where(
                    Candidate.phone.isnot(None), Candidate.phone.like(f"%{digits}%"), Candidate.is_deleted.is_(False)
                )
            )

    created = candidate is None
    if candidate is None:
        candidate = Candidate(full_name=personal.full_name or _fallback_name(resume))
        candidate.status = CandidateStatus.PENDING_REVIEW.value
        candidate.owner_id = resume.uploaded_by_id
        session.add(candidate)

    if personal.full_name:
        candidate.full_name = personal.full_name
    candidate.email = (personal.email or candidate.email or "").lower() or None
    candidate.phone = personal.phone or candidate.phone
    candidate.address = personal.address or candidate.address
    candidate.city = personal.city or candidate.city
    candidate.state = personal.state or candidate.state
    candidate.country = personal.country or candidate.country
    candidate.linkedin_url = personal.linkedin_url or candidate.linkedin_url
    candidate.github_url = personal.github_url or candidate.github_url
    candidate.portfolio_url = personal.portfolio_url or candidate.portfolio_url
    candidate.headline = personal.headline or candidate.headline
    candidate.current_title = parsed.current_title or candidate.current_title
    candidate.total_experience_years = parsed.total_experience_years or candidate.total_experience_years or 0.0
    candidate.highest_degree = parsed.highest_degree or candidate.highest_degree
    candidate.languages = parsed.languages or candidate.languages

    if parsed.current_company:
        company = _get_or_create_company(session, parsed.current_company)
        candidate.current_company_id = company.id
        candidate.current_company_name = company.name

    if created:
        candidate.status = CandidateStatus.PENDING_REVIEW.value
    session.flush()
    return candidate


def _fallback_name(resume: Resume) -> str:
    stem = resume.original_filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    cleaned = " ".join(part for part in stem.split() if not part.isdigit())
    return title_case(cleaned)[:120] or "Unknown Candidate"


def _get_or_create_company(session: Session, name: str) -> Company:
    normalized = normalize_key(name)
    company = session.scalar(select(Company).where(Company.normalized_name == normalized))
    if company is None:
        company = Company(name=name.strip()[:250], normalized_name=normalized)
        session.add(company)
        session.flush()
    return company


def _replace_experiences(session: Session, candidate: Candidate, parsed: ParsedResume) -> None:
    for existing in list(candidate.experiences):
        session.delete(existing)
    session.flush()
    for item in parsed.experiences:
        company = _get_or_create_company(session, item.company_name)
        if item.technologies:
            merged = list(dict.fromkeys([*(company.technologies or []), *item.technologies]))
            company.technologies = merged[:60]
        session.add(
            Experience(
                candidate_id=candidate.id,
                company_id=company.id,
                company_name=company.name,
                job_title=item.job_title,
                employment_type=item.employment_type,
                location=item.location,
                start_date=item.start_date,
                end_date=item.end_date,
                is_current=item.is_current,
                duration_months=item.duration_months,
                description=item.description,
                technologies=item.technologies or None,
            )
        )
    session.flush()


def _replace_educations(session: Session, candidate: Candidate, parsed: ParsedResume) -> None:
    for existing in list(candidate.educations):
        session.delete(existing)
    session.flush()
    for item in parsed.educations:
        session.add(
            Education(
                candidate_id=candidate.id,
                degree=item.degree,
                field_of_study=item.field_of_study,
                institution=item.institution,
                location=item.location,
                start_year=item.start_year,
                graduation_year=item.graduation_year,
                grade=item.grade,
                description=item.description,
            )
        )
    session.flush()


def _replace_projects(session: Session, candidate: Candidate, parsed: ParsedResume) -> None:
    for existing in list(candidate.projects):
        session.delete(existing)
    session.flush()
    for item in parsed.projects:
        session.add(
            Project(
                candidate_id=candidate.id,
                name=item.name[:250],
                role=item.role,
                description=item.description,
                technologies=item.technologies or None,
                url=item.url,
            )
        )
    session.flush()


def _replace_certifications(session: Session, candidate: Candidate, parsed: ParsedResume) -> None:
    for existing in list(candidate.certifications):
        session.delete(existing)
    session.flush()
    for item in parsed.certifications:
        session.add(
            Certification(
                candidate_id=candidate.id,
                name=item.name[:250],
                normalized_name=normalize_key(item.name),
                issuer=item.issuer,
                credential_id=item.credential_id,
                issue_date=item.issue_date,
                expiry_date=item.expiry_date,
                url=item.url,
            )
        )
    session.flush()


def _persist_skills(
    session: Session, candidate: Candidate, parsed: ParsedResume, full_text: str
) -> tuple[int, int]:
    """Normalize every skill mention against the taxonomy and store with evidence."""
    taxonomy = get_taxonomy(session)

    for existing in list(candidate.skills):
        session.delete(existing)
    session.flush()

    records: dict[str, dict[str, Any]] = {}

    def register(
        *,
        raw: str,
        skill_id: int | None,
        canonical: str,
        source: str,
        confidence: float,
        evidence: str | None,
        years: float | None,
        mentions: int,
    ) -> None:
        key = f"skill:{skill_id}" if skill_id else f"raw:{normalize_key(raw)}"
        entry = records.get(key)
        if entry is None:
            records[key] = {
                "raw": raw,
                "skill_id": skill_id,
                "canonical": canonical,
                "source": source,
                "confidence": confidence,
                "evidence": evidence,
                "years": years,
                "mentions": mentions,
            }
            return
        entry["mentions"] += mentions
        entry["confidence"] = max(entry["confidence"], confidence)
        entry["years"] = entry["years"] or years
        entry["evidence"] = entry["evidence"] or evidence
        if entry["source"] != SkillSource.RESUME_SKILLS_SECTION.value and source == SkillSource.RESUME_SKILLS_SECTION.value:
            entry["source"] = source

    # 1. Explicit skill mentions from the parser.
    for mention in parsed.skill_mentions:
        match = taxonomy.resolve(mention.raw_text)
        register(
            raw=mention.raw_text,
            skill_id=match.skill.id if match else None,
            canonical=match.skill.name if match else title_case(mention.raw_text),
            source=mention.source,
            confidence=mention.confidence * (1.0 if match else 0.7),
            evidence=mention.evidence,
            years=mention.years_experience,
            mentions=mention.mention_count,
        )

    # 2. Taxonomy scan of experience/project text finds implied skills.
    scan_sources = {
        "experience": SkillSource.RESUME_EXPERIENCE.value,
        "projects": SkillSource.RESUME_PROJECT.value,
        "certifications": SkillSource.RESUME_CERTIFICATION.value,
        "summary": SkillSource.RESUME_EXPERIENCE.value,
    }
    for section_name, source in scan_sources.items():
        section_text = parsed.sections.get(section_name)
        if not section_text:
            continue
        for match in taxonomy.scan_text(section_text):
            register(
                raw=match.matched_text,
                skill_id=match.skill.id,
                canonical=match.skill.name,
                source=source,
                confidence=min(0.9, match.confidence * 0.85),
                evidence=match.evidence,
                years=None,
                mentions=1,
            )

    # 3. Whole-document sweep as a safety net for unsectioned resumes.
    if len(records) < 5:
        for match in taxonomy.scan_text(full_text):
            register(
                raw=match.matched_text,
                skill_id=match.skill.id,
                canonical=match.skill.name,
                source=SkillSource.SEMANTIC_INFERENCE.value,
                confidence=0.7,
                evidence=match.evidence,
                years=None,
                mentions=1,
            )

    lowered_text = full_text.lower()
    normalized_count = 0
    for entry in records.values():
        canonical = entry["canonical"]
        proficiency = _infer_proficiency(canonical, lowered_text, entry["years"])
        if entry["skill_id"]:
            normalized_count += 1
        session.add(
            CandidateSkill(
                candidate_id=candidate.id,
                skill_id=entry["skill_id"],
                raw_text=str(entry["raw"])[:250],
                normalized_name=normalize_key(canonical)[:250],
                proficiency=proficiency.value,
                years_experience=entry["years"],
                source=entry["source"],
                confidence=round(min(1.0, entry["confidence"]), 3),
                evidence=entry["evidence"],
                mention_count=entry["mentions"],
                is_primary=entry["source"] == SkillSource.RESUME_SKILLS_SECTION.value and entry["mentions"] >= 1,
            )
        )
    session.flush()
    return len(records), normalized_count


def _infer_proficiency(skill_name: str, lowered_text: str, years: float | None) -> ProficiencyLevel:
    if years is not None:
        if years >= 8:
            return ProficiencyLevel.EXPERT
        if years >= 4:
            return ProficiencyLevel.ADVANCED
        if years >= 2:
            return ProficiencyLevel.INTERMEDIATE
        return ProficiencyLevel.BEGINNER

    name = skill_name.lower()
    position = lowered_text.find(name)
    if position >= 0:
        window = lowered_text[max(0, position - 90) : position + len(name) + 40]
        for hints, level in PROFICIENCY_HINTS:
            if any(hint in window for hint in hints):
                return level
    return ProficiencyLevel.INTERMEDIATE


def _completeness(candidate: Candidate, parsed: ParsedResume) -> float:
    checks = [
        bool(candidate.full_name and candidate.full_name != "Unknown Candidate"),
        bool(candidate.email),
        bool(candidate.phone),
        bool(candidate.city or candidate.country or candidate.address),
        bool(candidate.current_title),
        bool(candidate.current_company_name),
        candidate.total_experience_years > 0,
        bool(candidate.highest_degree),
        len(parsed.skill_mentions) >= 3,
        bool(parsed.experiences),
        bool(parsed.educations),
        bool(parsed.projects or parsed.certifications),
    ]
    return round(sum(1 for check in checks if check) / len(checks), 3)


def _highlights(candidate: Candidate, parsed: ParsedResume) -> list[str]:
    highlights: list[str] = []
    if candidate.total_experience_years:
        highlights.append(f"{candidate.total_experience_years} years of professional experience")
    if candidate.current_title and candidate.current_company_name:
        highlights.append(f"Currently {candidate.current_title} at {candidate.current_company_name}")
    primary = [link.display_name for link in candidate.skills if link.is_primary][:6]
    if primary:
        highlights.append("Core stack: " + ", ".join(primary))
    if parsed.certifications:
        highlights.append(f"{len(parsed.certifications)} certification(s)")
    if parsed.projects:
        highlights.append(f"{len(parsed.projects)} documented project(s)")
    if candidate.highest_degree:
        highlights.append(f"Education: {candidate.highest_degree}")
    return highlights[:6]


# ------------------------------------------------------------------- embeddings
def generate_candidate_embeddings(session: Session, candidate: Candidate, resume: Resume | None = None) -> int:
    """Embed the candidate document, resume chunks, projects and certifications."""
    embedder = get_embedder()
    store = get_vector_store()

    skills = [link.display_name for link in candidate.skills]
    titles = [experience.job_title for experience in candidate.experiences if experience.job_title]
    companies = [experience.company_name for experience in candidate.experiences]
    projects = [
        f"{project.name}: {truncate(project.description or '', 200)} [{', '.join(map(str, project.technologies or []))}]"
        for project in candidate.projects
    ]
    certifications = [certification.name for certification in candidate.certifications]
    education = [
        " ".join(filter(None, [item.degree, item.field_of_study, item.institution]))
        for item in candidate.educations
    ]

    document = build_candidate_document(
        name=candidate.full_name,
        headline=candidate.headline or candidate.current_title,
        summary=candidate.ai_summary,
        skills=skills,
        titles=titles,
        companies=companies,
        projects=projects,
        certifications=certifications,
        education=education,
        experience_years=candidate.total_experience_years,
    )

    records: list[VectorRecord] = [
        VectorRecord(
            kind=EmbeddingKind.RESUME.value,
            object_type="candidate",
            object_id=candidate.id,
            candidate_id=candidate.id,
            vector=embedder.encode(document),
            text_snippet=truncate(document, 900),
            meta={"skills": skills[:40], "experience_years": candidate.total_experience_years},
        )
    ]

    if resume is not None and resume.raw_text:
        for index, chunk in enumerate(chunk_text(resume.raw_text)[:24]):
            records.append(
                VectorRecord(
                    kind=EmbeddingKind.RESUME_CHUNK.value,
                    object_type="resume",
                    object_id=resume.id,
                    candidate_id=candidate.id,
                    chunk_index=index,
                    vector=embedder.encode(chunk),
                    text_snippet=truncate(chunk, 600),
                    meta={"resume_uuid": resume.uuid},
                )
            )

    for project in candidate.projects:
        text = " ".join(
            filter(None, [project.name, project.role, project.description, ", ".join(map(str, project.technologies or []))])
        )
        records.append(
            VectorRecord(
                kind=EmbeddingKind.PROJECT.value,
                object_type="project",
                object_id=project.id,
                candidate_id=candidate.id,
                vector=embedder.encode(text),
                text_snippet=truncate(text, 500),
            )
        )

    for certification in candidate.certifications:
        text = " ".join(filter(None, [certification.name, certification.issuer]))
        records.append(
            VectorRecord(
                kind=EmbeddingKind.CERTIFICATION.value,
                object_type="certification",
                object_id=certification.id,
                candidate_id=candidate.id,
                vector=embedder.encode(text),
                text_snippet=truncate(text, 300),
            )
        )

    return store.upsert(session, records, model=embedder.model_name)


def embed_skill_taxonomy(session: Session, *, limit: int | None = None) -> int:
    """Embed skill names + descriptions so skills themselves are semantically searchable."""
    from app.models.skill import Skill

    embedder = get_embedder()
    store = get_vector_store()
    statement = select(Skill)
    if limit:
        statement = statement.limit(limit)

    records: list[VectorRecord] = []
    for skill in session.scalars(statement):
        text = " ".join(
            filter(
                None,
                [
                    skill.name,
                    skill.category.name if skill.category else None,
                    skill.technology_stack,
                    skill.description,
                    " ".join(synonym.synonym for synonym in skill.synonyms),
                ],
            )
        )
        records.append(
            VectorRecord(
                kind=EmbeddingKind.SKILL.value,
                object_type="skill",
                object_id=skill.id,
                vector=embedder.encode(text),
                text_snippet=truncate(text, 400),
                meta={"category": skill.category.name if skill.category else None},
            )
        )
    written = store.upsert(session, records, model=embedder.model_name)
    logger.info("embedded %s taxonomy skills", written)
    return written


def reprocess_candidate(session: Session, candidate_id: int) -> ProcessingResult:
    """Re-run the pipeline for a candidate's latest resume (after a taxonomy update)."""
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundError(f"Candidate {candidate_id} not found")
    resume = candidate.latest_resume
    if resume is None:
        raise NotFoundError(f"Candidate {candidate_id} has no resume to reprocess")
    return process_resume(session, resume.id)
