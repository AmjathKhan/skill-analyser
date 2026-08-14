"""Aggregated API router mounted under the configured API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    candidates,
    dashboard,
    graph,
    health,
    jobs,
    matching,
    reports,
    resumes,
    search,
    skills,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(candidates.router)
api_router.include_router(search.router)
api_router.include_router(matching.router)
api_router.include_router(graph.router)
api_router.include_router(skills.router)
api_router.include_router(jobs.router)
api_router.include_router(dashboard.router)
api_router.include_router(reports.router)
