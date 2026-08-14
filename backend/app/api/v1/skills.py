"""Skills knowledge base endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession, require_permission
from app.core.config import settings
from app.models.candidate import CandidateSkill
from app.models.skill import Skill
from app.models.user import User
from app.schemas.skill import SkillCategoryRead, SkillImportResponse, SkillTaxonomyRead
from app.services.resume_processing import embed_skill_taxonomy
from app.services.skills_import import import_skills_csv
from app.services.taxonomy import get_taxonomy

router = APIRouter(prefix="/skills", tags=["Skills Knowledge Base"])

ReadPermission = Annotated[User, Depends(require_permission("graph:read"))]


def _candidate_counts(session) -> dict[int, int]:
    return dict(
        session.execute(
            select(CandidateSkill.skill_id, func.count(func.distinct(CandidateSkill.candidate_id)))
            .where(CandidateSkill.skill_id.isnot(None))
            .group_by(CandidateSkill.skill_id)
        ).all()
    )


@router.get("", response_model=list[SkillTaxonomyRead])
def list_skills(
    session: DbSession,
    _: ReadPermission,
    search: str | None = Query(None, min_length=1, max_length=80),
    category: str | None = None,
    technology_stack: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
) -> list[SkillTaxonomyRead]:
    taxonomy = get_taxonomy(session)
    counts = _candidate_counts(session)
    lowered = (search or "").lower()

    results: list[SkillTaxonomyRead] = []
    for node in taxonomy.all_skills():
        if lowered and lowered not in node.name.lower() and not any(
            lowered in synonym.lower() for synonym in node.synonyms
        ):
            continue
        if category and (node.category or "").lower() != category.lower():
            continue
        if technology_stack and (node.technology_stack or "").lower() != technology_stack.lower():
            continue
        parent = taxonomy.get(node.parent_id) if node.parent_id else None
        results.append(
            SkillTaxonomyRead(
                id=node.id,
                name=node.name,
                slug=node.slug,
                category=node.category,
                parent_skill=parent.name if parent else None,
                technology_stack=node.technology_stack,
                experience_level=node.experience_level,
                description=node.description,
                is_technical=node.is_technical,
                synonyms=list(node.synonyms),
                related_skills=[
                    related.name
                    for related in (taxonomy.get(related_id) for related_id in node.related_ids)
                    if related
                ],
                job_roles=list(node.job_roles),
                candidate_count=int(counts.get(node.id, 0)),
            )
        )
        if len(results) >= limit:
            break
    results.sort(key=lambda item: (-item.candidate_count, item.name))
    return results


@router.get("/categories", response_model=list[SkillCategoryRead])
def list_categories(session: DbSession, _: ReadPermission) -> list[SkillCategoryRead]:
    taxonomy = get_taxonomy(session)
    categories = taxonomy.categories()
    from app.models.skill import SkillCategory

    rows = {category.name: category for category in session.scalars(select(SkillCategory))}
    return sorted(
        [
            SkillCategoryRead(
                id=rows[name].id if name in rows else 0,
                name=name,
                description=rows[name].description if name in rows else None,
                skill_count=len(nodes),
            )
            for name, nodes in categories.items()
        ],
        key=lambda item: -item.skill_count,
    )


@router.post("/import", response_model=SkillImportResponse)
def import_skills(
    session: DbSession,
    _: AdminUser,
    path: str | None = Query(None, description="Server-side CSV path (defaults to SKILLS_CSV_PATH)"),
    generate_embeddings: bool = Query(True, description="Embed skills for semantic search after import"),
) -> SkillImportResponse:
    """Re-import the Skills CSV. Idempotent: existing skills are updated in place."""
    report = import_skills_csv(session, path or settings.skills_csv)
    get_taxonomy(session, refresh=True)
    embeddings = embed_skill_taxonomy(session) if generate_embeddings else 0
    return SkillImportResponse(**report.as_dict(), embeddings_created=embeddings)


@router.post("/import/upload", response_model=SkillImportResponse)
def upload_skills_csv(
    session: DbSession,
    _: AdminUser,
    file: Annotated[UploadFile, File(description="Skills CSV")],
    generate_embeddings: bool = Query(True),
) -> SkillImportResponse:
    data = file.file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as handle:
        handle.write(data)
        temp_path = Path(handle.name)
    try:
        report = import_skills_csv(session, temp_path)
        report.source = file.filename or "uploaded.csv"
        get_taxonomy(session, refresh=True)
        embeddings = embed_skill_taxonomy(session) if generate_embeddings else 0
        return SkillImportResponse(**report.as_dict(), embeddings_created=embeddings)
    finally:
        temp_path.unlink(missing_ok=True)
        file.file.close()


@router.get("/stats", response_model=dict)
def skill_stats(session: DbSession, _: ReadPermission) -> dict:
    taxonomy = get_taxonomy(session)
    total = session.scalar(select(func.count(Skill.id))) or 0
    links = session.scalar(select(func.count(CandidateSkill.id))) or 0
    mapped = session.scalar(select(func.count(CandidateSkill.id)).where(CandidateSkill.skill_id.isnot(None))) or 0
    return {
        "taxonomy_size": total,
        "categories": len(taxonomy.categories()),
        "candidate_skill_links": links,
        "mapped_to_taxonomy": mapped,
        "coverage_percent": round(100 * mapped / links, 2) if links else 0.0,
        "source_csv": str(settings.skills_csv),
    }
