"""Vector persistence + similarity search.

Vectors are always written to ``embeddings.vector_json`` so the corpus is
durable and portable. Search is served by one of three backends:

* ``pgvector`` - ANN/exact search inside PostgreSQL via the ``<=>`` operator.
* ``faiss``    - in-process FAISS ``IndexFlatIP`` built from the table.
* ``numpy``    - in-process matrix dot-product (default, no extra deps).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.ai.embeddings import l2_normalize
from app.core.config import VectorBackend, settings
from app.core.logging import get_logger
from app.models.ai import Embedding

logger = get_logger(__name__)


@dataclass(slots=True)
class VectorRecord:
    kind: str
    object_type: str
    object_id: int
    vector: np.ndarray
    candidate_id: int | None = None
    chunk_index: int = 0
    text_snippet: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VectorHit:
    embedding_id: int
    kind: str
    object_type: str
    object_id: int
    candidate_id: int | None
    score: float
    chunk_index: int = 0
    text_snippet: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class _MemoryIndex:
    """Cached matrix of persisted vectors, invalidated on write."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._matrix: np.ndarray | None = None
        self._rows: list[VectorHit] = []
        self._faiss_index: Any | None = None
        self._built_at: float = 0.0
        self._dirty = True

    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True

    def build(self, session: Session, *, use_faiss: bool) -> None:
        with self._lock:
            statement = select(Embedding).order_by(Embedding.id)
            rows: list[VectorHit] = []
            vectors: list[list[float]] = []
            for embedding in session.scalars(statement):
                vector = embedding.vector_json or []
                if not vector:
                    continue
                vectors.append(list(vector))
                rows.append(
                    VectorHit(
                        embedding_id=embedding.id,
                        kind=embedding.kind,
                        object_type=embedding.object_type,
                        object_id=embedding.object_id,
                        candidate_id=embedding.candidate_id,
                        score=0.0,
                        chunk_index=embedding.chunk_index,
                        text_snippet=embedding.text_snippet,
                        meta=embedding.meta or {},
                    )
                )
            self._rows = rows
            self._matrix = l2_normalize(np.asarray(vectors, dtype=np.float32)) if vectors else None
            self._faiss_index = None
            if use_faiss and self._matrix is not None:
                try:  # pragma: no cover - requires faiss
                    import faiss

                    index = faiss.IndexFlatIP(self._matrix.shape[1])
                    index.add(self._matrix)
                    self._faiss_index = index
                except Exception as exc:
                    logger.warning("faiss index build failed (%s); using numpy", exc.__class__.__name__)
            self._dirty = False
            self._built_at = time.time()
            logger.debug("vector index rebuilt with %s vectors", len(rows))

    def ensure(self, session: Session, *, use_faiss: bool) -> None:
        if self._dirty or self._matrix is None:
            self.build(session, use_faiss=use_faiss)

    def search(
        self,
        query: np.ndarray,
        *,
        top_k: int,
        kinds: set[str] | None,
        candidate_ids: set[int] | None,
    ) -> list[VectorHit]:
        with self._lock:
            if self._matrix is None or not self._rows:
                return []
            query = l2_normalize(np.asarray(query, dtype=np.float32))
            if query.shape[-1] != self._matrix.shape[1]:
                logger.warning(
                    "query dim %s != index dim %s - re-embed the corpus", query.shape[-1], self._matrix.shape[1]
                )
                return []

            mask = np.ones(len(self._rows), dtype=bool)
            if kinds:
                mask &= np.fromiter((row.kind in kinds for row in self._rows), bool, len(self._rows))
            if candidate_ids is not None:
                mask &= np.fromiter((row.candidate_id in candidate_ids for row in self._rows), bool, len(self._rows))
            indices = np.nonzero(mask)[0]
            if indices.size == 0:
                return []

            scores = self._matrix[indices] @ query
            order = np.argsort(-scores)[:top_k]
            hits: list[VectorHit] = []
            for position in order:
                row = self._rows[int(indices[position])]
                hits.append(
                    VectorHit(
                        embedding_id=row.embedding_id,
                        kind=row.kind,
                        object_type=row.object_type,
                        object_id=row.object_id,
                        candidate_id=row.candidate_id,
                        score=float(scores[position]),
                        chunk_index=row.chunk_index,
                        text_snippet=row.text_snippet,
                        meta=row.meta,
                    )
                )
            return hits

    @property
    def size(self) -> int:
        return len(self._rows)


_index = _MemoryIndex()


class VectorStore:
    """Facade over the configured vector backend."""

    def __init__(self, backend: VectorBackend | None = None) -> None:
        self.backend = backend or settings.vector_backend
        self._pgvector_ready: bool | None = None

    # ------------------------------------------------------------------ writes
    def upsert(self, session: Session, records: Iterable[VectorRecord], *, model: str) -> int:
        written = 0
        for record in records:
            vector = np.asarray(record.vector, dtype=np.float32).ravel()
            if vector.size == 0:
                continue
            payload = [round(float(value), 6) for value in vector.tolist()]
            existing = session.scalar(
                select(Embedding).where(
                    Embedding.object_type == record.object_type,
                    Embedding.object_id == record.object_id,
                    Embedding.kind == record.kind,
                    Embedding.chunk_index == record.chunk_index,
                )
            )
            if existing is None:
                existing = Embedding(
                    kind=record.kind,
                    object_type=record.object_type,
                    object_id=record.object_id,
                    chunk_index=record.chunk_index,
                )
                session.add(existing)
            existing.candidate_id = record.candidate_id
            existing.model = model
            existing.dim = len(payload)
            existing.vector_json = payload
            existing.text_snippet = record.text_snippet
            existing.meta = record.meta or None
            written += 1

        if written:
            session.flush()
            _index.invalidate()
            if self._use_pgvector(session):
                self._sync_pgvector(session)
        return written

    def delete_for(self, session: Session, *, object_type: str, object_id: int) -> None:
        session.execute(
            delete(Embedding).where(Embedding.object_type == object_type, Embedding.object_id == object_id)
        )
        _index.invalidate()

    def delete_for_candidate(self, session: Session, candidate_id: int) -> None:
        session.execute(delete(Embedding).where(Embedding.candidate_id == candidate_id))
        _index.invalidate()

    # ------------------------------------------------------------------ search
    def search(
        self,
        session: Session,
        query_vector: np.ndarray,
        *,
        top_k: int = 25,
        kinds: Sequence[str] | None = None,
        candidate_ids: Sequence[int] | None = None,
    ) -> list[VectorHit]:
        kind_set = set(kinds) if kinds else None
        id_set = {int(value) for value in candidate_ids} if candidate_ids is not None else None
        if id_set is not None and not id_set:
            return []

        if self._use_pgvector(session):
            hits = self._search_pgvector(session, query_vector, top_k=top_k, kinds=kind_set, candidate_ids=id_set)
            if hits is not None:
                return hits

        _index.ensure(session, use_faiss=self.backend is VectorBackend.faiss)
        return _index.search(query_vector, top_k=top_k, kinds=kind_set, candidate_ids=id_set)

    def rebuild_index(self, session: Session) -> int:
        _index.build(session, use_faiss=self.backend is VectorBackend.faiss)
        if self._use_pgvector(session):
            self._sync_pgvector(session)
        return _index.size

    def stats(self, session: Session) -> dict[str, Any]:
        _index.ensure(session, use_faiss=self.backend is VectorBackend.faiss)
        return {
            "backend": self.backend.value,
            "vectors": _index.size,
            "pgvector_active": bool(self._use_pgvector(session)),
        }

    # ---------------------------------------------------------------- pgvector
    def _use_pgvector(self, session: Session) -> bool:
        if self.backend is not VectorBackend.pgvector or settings.is_sqlite:
            return False
        if self._pgvector_ready is None:
            self._pgvector_ready = self._prepare_pgvector(session)
        return bool(self._pgvector_ready)

    def _prepare_pgvector(self, session: Session) -> bool:
        try:
            session.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            session.execute(
                sql_text(f"ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS vector vector({settings.embedding_dim})")
            )
            session.execute(
                sql_text(
                    "CREATE INDEX IF NOT EXISTS ix_embeddings_vector_cosine "
                    "ON embeddings USING hnsw (vector vector_cosine_ops)"
                )
            )
            session.commit()
            logger.info("pgvector search enabled (dim=%s)", settings.embedding_dim)
            return True
        except Exception as exc:
            session.rollback()
            logger.warning("pgvector unavailable (%s); falling back to in-process search", exc.__class__.__name__)
            return False

    def _sync_pgvector(self, session: Session) -> None:
        """Mirror vector_json into the native vector column for rows that changed."""
        try:
            session.execute(
                sql_text(
                    "UPDATE embeddings SET vector = vector_json::text::vector "
                    "WHERE vector IS NULL OR vector::text <> vector_json::text"
                )
            )
        except Exception as exc:
            session.rollback()
            self._pgvector_ready = False
            logger.warning("pgvector sync failed (%s); using in-process search", exc.__class__.__name__)

    def _search_pgvector(
        self,
        session: Session,
        query_vector: np.ndarray,
        *,
        top_k: int,
        kinds: set[str] | None,
        candidate_ids: set[int] | None,
    ) -> list[VectorHit] | None:
        vector_literal = "[" + ",".join(f"{float(value):.6f}" for value in np.asarray(query_vector).ravel()) + "]"
        clauses = ["vector IS NOT NULL"]
        params: dict[str, Any] = {"query": vector_literal, "limit": top_k}
        if kinds:
            clauses.append("kind = ANY(:kinds)")
            params["kinds"] = list(kinds)
        if candidate_ids is not None:
            clauses.append("candidate_id = ANY(:candidate_ids)")
            params["candidate_ids"] = list(candidate_ids)

        statement = sql_text(
            "SELECT id, kind, object_type, object_id, candidate_id, chunk_index, text_snippet, meta, "
            "1 - (vector <=> CAST(:query AS vector)) AS score "
            f"FROM embeddings WHERE {' AND '.join(clauses)} "
            "ORDER BY vector <=> CAST(:query AS vector) LIMIT :limit"
        )
        try:
            rows = session.execute(statement, params).mappings().all()
        except Exception as exc:
            session.rollback()
            self._pgvector_ready = False
            logger.warning("pgvector query failed (%s); falling back", exc.__class__.__name__)
            return None

        return [
            VectorHit(
                embedding_id=row["id"],
                kind=row["kind"],
                object_type=row["object_type"],
                object_id=row["object_id"],
                candidate_id=row["candidate_id"],
                score=float(row["score"] or 0.0),
                chunk_index=row["chunk_index"],
                text_snippet=row["text_snippet"],
                meta=row["meta"] or {},
            )
            for row in rows
        ]


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None
    _index.invalidate()
