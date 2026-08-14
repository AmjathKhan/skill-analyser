"""Embedding generation and vector search tests (deterministic hash backend)."""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.ai.embeddings import HashEmbedder, cosine_similarity, get_embedder, l2_normalize
from app.ai.vector_store import VectorRecord, get_vector_store


def test_hash_embedder_is_deterministic() -> None:
    embedder = HashEmbedder(dim=128)
    first = embedder.encode_one("Python FastAPI PostgreSQL")
    second = embedder.encode_one("Python FastAPI PostgreSQL")
    assert first.shape == (128,)
    assert np.allclose(first, second)


def test_embeddings_are_l2_normalized() -> None:
    vector = get_embedder().encode_one("ReactJS TypeScript Material UI")
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-5


def test_similar_texts_score_higher_than_unrelated() -> None:
    embedder = HashEmbedder(dim=384)
    query = embedder.encode_one("python fastapi postgresql backend engineer")
    close = embedder.encode_one("backend engineer with python fastapi and postgresql")
    far = embedder.encode_one("graphic designer illustrator photoshop typography")
    assert cosine_similarity(query, close) > cosine_similarity(query, far)


def test_batch_encode_matches_single_encode() -> None:
    embedder = HashEmbedder(dim=64)
    texts = ["docker kubernetes", "spark airflow"]
    batch = embedder.encode(texts)
    assert batch.shape == (2, 64)
    for index, text in enumerate(texts):
        assert np.allclose(batch[index], embedder.encode_one(text), atol=1e-6)


def test_l2_normalize_handles_zero_vector() -> None:
    normalized = l2_normalize(np.zeros(8, dtype=np.float32))
    assert not np.isnan(normalized).any()


def test_vector_store_upsert_search_and_delete(client, db_session: Session) -> None:
    store = get_vector_store()
    embedder = get_embedder()

    records = [
        VectorRecord(
            kind="resume",
            object_type="test_candidate",
            object_id=9001,
            candidate_id=None,
            vector=embedder.encode_one("python fastapi postgresql docker aws"),
            text_snippet="backend engineer",
        ),
        VectorRecord(
            kind="resume",
            object_type="test_candidate",
            object_id=9002,
            candidate_id=None,
            vector=embedder.encode_one("figma illustrator branding typography"),
            text_snippet="designer",
        ),
    ]
    written = store.upsert(db_session, records, model=embedder.model_name)
    db_session.flush()
    assert written == 2

    query = embedder.encode_one("python backend engineer with fastapi")
    hits = store.search(db_session, query, top_k=5, kinds=["resume"])
    matched = [hit for hit in hits if hit.object_type == "test_candidate"]
    assert matched, "the freshly written vectors should be searchable"
    assert matched[0].object_id == 9001
    assert -1.01 <= matched[0].score <= 1.01

    # Re-upserting the same object must update in place rather than duplicate.
    assert store.upsert(db_session, records[:1], model=embedder.model_name) == 1
    db_session.flush()

    for record in records:
        store.delete_for(db_session, object_type=record.object_type, object_id=record.object_id)
    db_session.flush()
    remaining = [
        hit
        for hit in store.search(db_session, query, top_k=10, kinds=["resume"])
        if hit.object_type == "test_candidate"
    ]
    assert remaining == []


def test_vector_store_stats(client, db_session: Session) -> None:
    stats = get_vector_store().stats(db_session)
    assert stats["backend"] in {"numpy", "faiss", "pgvector"}
    assert stats["vectors"] >= 0
