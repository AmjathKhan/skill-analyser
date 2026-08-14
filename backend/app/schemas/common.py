"""Shared response envelopes."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False

    @classmethod
    def build(cls, *, page: int, page_size: int, total: int) -> PageMeta:
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    meta: PageMeta = Field(default_factory=PageMeta)


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class CountResponse(BaseModel):
    count: int = 0


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: bool
    graph_backend: str
    graph_healthy: bool
    vector_backend: str
    embedding_model: str
    llm_backend: str
    skills_loaded: int
    celery_enabled: bool
