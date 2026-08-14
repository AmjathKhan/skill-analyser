"""Celery tasks. Each task owns its database session."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from app.core.logging import get_logger
from app.db.session import session_scope

logger = get_logger(__name__)


@shared_task(name="resume.process", bind=True, max_retries=2, default_retry_delay=30)
def process_resume_task(self, resume_id: int, actor_id: int | None = None) -> dict[str, Any]:
    """Full pipeline for one uploaded resume."""
    from app.services.resume_processing import process_resume

    logger.info("task resume.process starting for resume %s", resume_id)
    with session_scope() as session:
        result = process_resume(session, resume_id, actor_id=actor_id)
    if result.error and self.request.retries < (self.max_retries or 0):
        # Transient issues (locked file, cold model download) are worth a retry.
        raise self.retry(exc=RuntimeError(result.error))
    return result.as_dict()


@shared_task(name="graph.rebuild")
def rebuild_graph_task(clear: bool = True) -> dict[str, Any]:
    from app.graph.builder import KnowledgeGraphBuilder

    with session_scope() as session:
        return KnowledgeGraphBuilder(session).build_full(clear=clear).as_dict()


@shared_task(name="embeddings.rebuild")
def rebuild_candidate_embeddings_task(candidate_id: int | None = None) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.candidate import Candidate
    from app.services.resume_processing import generate_candidate_embeddings

    written = 0
    with session_scope() as session:
        statement = select(Candidate).where(Candidate.is_deleted.is_(False))
        if candidate_id:
            statement = statement.where(Candidate.id == candidate_id)
        for candidate in session.scalars(statement):
            written += generate_candidate_embeddings(session, candidate, candidate.latest_resume)
    return {"embeddings_written": written}


@shared_task(name="embeddings.reindex")
def reindex_vectors_task() -> dict[str, Any]:
    from app.ai.vector_store import get_vector_store

    with session_scope() as session:
        size = get_vector_store().rebuild_index(session)
    return {"vectors_indexed": size}


@shared_task(name="skills.import")
def import_skills_task(path: str | None = None) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.resume_processing import embed_skill_taxonomy
    from app.services.skills_import import import_skills_csv
    from app.services.taxonomy import get_taxonomy

    with session_scope() as session:
        report = import_skills_csv(session, path or settings.skills_csv)
        get_taxonomy(session, refresh=True)
        embeddings = embed_skill_taxonomy(session)
    return {**report.as_dict(), "embeddings_created": embeddings}
