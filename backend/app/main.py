"""FastAPI application factory: middleware, lifespan and OpenAPI metadata."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import Environment, settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.session import check_database, ensure_extensions, session_scope

logger = get_logger(__name__)

DESCRIPTION = """
**AI Skill Analyser** - a Graph RAG based HR recruitment platform.

* Upload resumes (PDF / DOC / DOCX) and extract candidates with AI
* Normalize skills against an authoritative Skills CSV taxonomy
* Build a knowledge graph of candidates, skills, technologies, companies,
  certifications, projects, education and job roles
* Retrieve with Graph RAG (graph traversal + vector similarity)
* Rank candidates with an explainable, weighted match score

Authenticate with `POST /api/login`, then send `Authorization: Bearer <access_token>`.
"""

TAGS_METADATA = [
    {"name": "System", "description": "Health and configuration introspection."},
    {"name": "Authentication", "description": "JWT login, refresh, logout and password reset."},
    {"name": "User Management", "description": "HR Admin user administration and audit logs."},
    {"name": "Resumes", "description": "Upload, download and reprocess resume files."},
    {"name": "Candidates", "description": "Candidate list, profile, editing and notes."},
    {"name": "Search", "description": "Semantic, keyword, graph and hybrid candidate search."},
    {"name": "AI Skill Matching", "description": "Explainable candidate ranking and skill gap analysis."},
    {"name": "Knowledge Graph", "description": "Graph build, traversal and visualization data."},
    {"name": "Skills Knowledge Base", "description": "Skill taxonomy browsing and CSV import."},
    {"name": "Job Requirements", "description": "Reusable job requirement definitions."},
    {"name": "Dashboard", "description": "Cards, charts and activity feed."},
    {"name": "Reports", "description": "Recruitment analytics with PDF/Excel/CSV export."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger.info("starting %s v%s (%s)", settings.app_name, settings.app_version, settings.environment.value)
    settings.ensure_directories()

    if check_database():
        ensure_extensions()
        try:
            with session_scope() as session:
                from app.services.skills_import import import_skills_csv, skills_table_is_empty
                from app.services.taxonomy import get_taxonomy

                if settings.auto_import_skills and skills_table_is_empty(session):
                    if settings.skills_csv.exists():
                        report = import_skills_csv(session, settings.skills_csv)
                        logger.info("imported skills taxonomy: %s", report.as_dict())
                    else:
                        logger.warning("skills CSV not found at %s", settings.skills_csv)
                get_taxonomy(session, refresh=True)
        except Exception as exc:
            logger.warning("skills bootstrap skipped: %s", exc)

        try:
            with session_scope() as session:
                from app.services.graph_service import ensure_hydrated

                ensure_hydrated(session)
        except Exception as exc:
            logger.warning("graph hydration skipped: %s", exc)
    else:
        logger.warning("database unreachable at startup - endpoints will report degraded health")

    yield

    from app.graph.registry import reset_graph

    reset_graph()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={"name": "AI Skill Analyser", "url": "https://example.com"},
        license_info={"name": "Proprietary"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.environment is Environment.production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
        # Defence-in-depth headers (the SPA is served by nginx in production).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        if settings.environment is Environment.production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if duration_ms > 3000:
            logger.warning("slow request %s %s took %.0fms", request.method, request.url.path, duration_ms)
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    frontend_dist = _frontend_dist_dir()
    if frontend_dist is not None:
        _mount_spa(app, frontend_dist)
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "name": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
                "health": f"{settings.api_prefix}/health",
            }

    return app


def _frontend_dist_dir() -> Path | None:
    raw = settings.frontend_dist
    if not raw:
        return None
    dist = Path(raw)
    if not dist.is_absolute():
        dist = (Path(__file__).resolve().parents[2] / dist).resolve()
    if (dist / "index.html").is_file():
        return dist
    return None


def _mount_spa(app: FastAPI, dist: Path) -> None:
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def spa_index():
        return FileResponse(dist / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
            return FileResponse(dist / "index.html")
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
