"""Graph backend selection with automatic fallback to NetworkX."""

from __future__ import annotations

import threading
from contextlib import suppress

from app.core.config import GraphBackend as GraphBackendSetting
from app.core.config import settings
from app.core.logging import get_logger
from app.graph.base import GraphBackend
from app.graph.networkx_backend import NetworkXGraphBackend

logger = get_logger(__name__)

_backend: GraphBackend | None = None
_hydrated = False
_lock = threading.RLock()


def get_graph() -> GraphBackend:
    global _backend
    if _backend is not None:
        return _backend
    with _lock:
        if _backend is not None:
            return _backend
        if settings.graph_backend is GraphBackendSetting.neo4j:
            try:
                from app.graph.neo4j_backend import Neo4jGraphBackend

                _backend = Neo4jGraphBackend()
            except Exception as exc:
                logger.warning(
                    "Neo4j unavailable (%s: %s) - falling back to the in-process NetworkX graph",
                    exc.__class__.__name__,
                    exc,
                )
                _backend = NetworkXGraphBackend()
        else:
            _backend = NetworkXGraphBackend()
        logger.info("graph backend: %s", _backend.name)
    return _backend


def active_backend_name() -> str:
    return get_graph().name


def requires_hydration() -> bool:
    """NetworkX lives in memory, so it must be rebuilt from PostgreSQL on boot."""
    return isinstance(get_graph(), NetworkXGraphBackend) and not _hydrated


def mark_hydrated(value: bool = True) -> None:
    global _hydrated
    with _lock:
        _hydrated = value


def reset_graph() -> None:
    global _backend, _hydrated
    with _lock:
        closer = getattr(_backend, "close", None)
        if callable(closer):
            with suppress(Exception):
                closer()
        _backend = None
        _hydrated = False
