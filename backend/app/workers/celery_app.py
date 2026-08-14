"""Celery application for background resume processing and graph maintenance."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging("INFO")

celery_app = Celery(
    "skill_analyser",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=900,
    task_soft_time_limit=780,
    result_expires=86400,
    task_default_queue="skill_analyser",
    task_routes={
        "resume.process": {"queue": "skill_analyser"},
        "graph.rebuild": {"queue": "skill_analyser"},
        "embeddings.rebuild": {"queue": "skill_analyser"},
    },
    beat_schedule={
        "nightly-graph-rebuild": {
            "task": "graph.rebuild",
            "schedule": crontab(hour=2, minute=30),
        },
        "nightly-vector-reindex": {
            "task": "embeddings.reindex",
            "schedule": crontab(hour=3, minute=15),
        },
    },
)
