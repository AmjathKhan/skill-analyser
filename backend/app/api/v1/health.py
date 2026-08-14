"""Health and system information endpoints (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.ai.embeddings import get_embedder
from app.ai.vector_store import get_vector_store
from app.api.deps import DbSession
from app.core.config import settings
from app.db.session import check_database
from app.graph.registry import get_graph
from app.models.skill import Skill
from app.schemas.common import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def health(session: DbSession) -> HealthResponse:
    database_ok = check_database()
    graph = get_graph()
    graph_stats = graph.stats()
    skills = session.scalar(select(func.count(Skill.id))) or 0 if database_ok else 0

    return HealthResponse(
        status="ok" if database_ok else "degraded",
        version=settings.app_version,
        environment=settings.environment.value,
        database=database_ok,
        graph_backend=graph.name,
        graph_healthy=graph_stats.healthy,
        vector_backend=settings.vector_backend.value,
        embedding_model=get_embedder().model_name,
        llm_backend=settings.llm_backend.value,
        skills_loaded=skills,
        celery_enabled=settings.use_celery,
    )


@router.get("/system/info", response_model=dict)
def system_info(session: DbSession) -> dict:
    graph = get_graph()
    return {
        "app": {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment.value,
            "api_prefix": settings.api_prefix,
        },
        "ai": {
            "embedding_backend": settings.embedding_backend.value,
            "embedding_model": get_embedder().model_name,
            "embedding_dim": get_embedder().dim,
            "vector": get_vector_store().stats(session),
            "llm_backend": settings.llm_backend.value,
            "llm_model": settings.llm_model if settings.llm_backend.value == "openai" else "deterministic-template",
            "spacy_model": settings.spacy_model,
            "ocr_enabled": settings.enable_ocr,
        },
        "graph": graph.stats().as_dict(),
        "matching_weights": settings.match_weights,
        "uploads": {
            "max_size_mb": settings.max_upload_size_mb,
            "allowed_extensions": sorted(settings.upload_extensions),
            "encrypted_at_rest": settings.file_encryption_enabled,
        },
    }
