"""Embedding generation.

Two interchangeable backends:

* ``sentence-transformers`` - real semantic embeddings (default in Docker).
* ``hash`` - deterministic feature-hashing embeddings with no model download,
  so the platform boots, tests and demos fully offline.
"""

from __future__ import annotations

import hashlib
import math
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np

from app.ai.text_utils import normalize_key, tokenize
from app.core.config import EmbeddingBackend, settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseEmbedder(ABC):
    model_name: str = "unknown"
    dim: int = 384

    @abstractmethod
    def _encode(self, texts: Sequence[str]) -> np.ndarray: ...

    def encode(self, texts: Sequence[str] | str, *, normalize: bool = True) -> np.ndarray:
        single = isinstance(texts, str)
        raw: Sequence[str] = [texts] if isinstance(texts, str) else list(texts)
        batch = [(text or "").strip() for text in raw]
        if not batch:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self._encode(batch).astype(np.float32, copy=False)
        if normalize:
            vectors = l2_normalize(vectors)
        return vectors[0] if single else vectors

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode(text)  # type: ignore[return-value]


class HashEmbedder(BaseEmbedder):
    """Feature hashing over word unigrams/bigrams plus character trigrams.

    Deterministic, dependency-free and stable across processes, which makes the
    vector store reproducible in CI. Lexical rather than semantic, so semantic
    scores are conservative - production deployments should use transformers.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.model_name = f"hash-{dim}"

    @staticmethod
    def _bucket(feature: str, dim: int) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % dim, 1.0 if (value >> 63) & 1 else -1.0

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = tokenize(text, drop_stopwords=True)
            features: list[tuple[str, float]] = []
            features.extend((f"w:{token}", 1.0) for token in tokens)
            features.extend(
                (f"b:{tokens[i]}_{tokens[i + 1]}", 0.7) for i in range(len(tokens) - 1)
            )
            key = normalize_key(text)[:4000]
            features.extend((f"c:{key[i : i + 3]}", 0.35) for i in range(max(0, len(key) - 2)))
            for feature, weight in features:
                index, sign = self._bucket(feature, self.dim)
                out[row, index] += sign * weight
            # Sub-linear scaling keeps long resumes comparable to short queries.
            out[row] = np.sign(out[row]) * np.log1p(np.abs(out[row]))
        return out


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(
            self._model.encode(list(texts), batch_size=16, show_progress_bar=False, convert_to_numpy=True)
        )


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    if vectors.ndim == 1:
        norm = float(np.linalg.norm(vectors))
        return vectors / norm if norm else vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def cosine_similarity(left: np.ndarray | list[float], right: np.ndarray | list[float]) -> float:
    a = np.asarray(left, dtype=np.float32)
    b = np.asarray(right, dtype=np.float32)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not denominator or math.isnan(denominator):
        return 0.0
    return float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))


_embedder: BaseEmbedder | None = None
_lock = threading.Lock()


def get_embedder() -> BaseEmbedder:
    """Process-wide embedder singleton (models are expensive to load)."""
    global _embedder
    if _embedder is not None:
        return _embedder
    with _lock:
        if _embedder is not None:
            return _embedder
        if settings.embedding_backend is EmbeddingBackend.sentence_transformers:
            try:
                _embedder = SentenceTransformerEmbedder(settings.embedding_model)
                logger.info("embeddings: sentence-transformers %s (dim=%s)", _embedder.model_name, _embedder.dim)
            except Exception as exc:
                logger.warning("sentence-transformers unavailable (%s); using hash embedder", exc.__class__.__name__)
                _embedder = HashEmbedder(settings.embedding_dim)
        else:
            _embedder = HashEmbedder(settings.embedding_dim)
            logger.info("embeddings: deterministic hash backend (dim=%s)", _embedder.dim)
    return _embedder


def reset_embedder() -> None:
    """Used by tests when switching backends."""
    global _embedder
    with _lock:
        _embedder = None


def build_candidate_document(
    *,
    name: str | None,
    headline: str | None,
    summary: str | None,
    skills: Sequence[str],
    titles: Sequence[str],
    companies: Sequence[str],
    projects: Sequence[str],
    certifications: Sequence[str],
    education: Sequence[str],
    experience_years: float | None = None,
) -> str:
    """Compose the canonical text that represents a candidate in vector space."""
    parts = [
        f"Candidate: {name or 'Unknown'}",
        f"Headline: {headline}" if headline else "",
        f"Experience: {experience_years} years" if experience_years is not None else "",
        f"Roles: {', '.join(dict.fromkeys(titles))}" if titles else "",
        f"Companies: {', '.join(dict.fromkeys(companies))}" if companies else "",
        f"Skills: {', '.join(dict.fromkeys(skills))}" if skills else "",
        f"Projects: {'; '.join(projects)}" if projects else "",
        f"Certifications: {', '.join(certifications)}" if certifications else "",
        f"Education: {', '.join(education)}" if education else "",
        f"Summary: {summary}" if summary else "",
    ]
    return "\n".join(part for part in parts if part)


def build_requirement_document(
    *,
    title: str | None,
    required_skills: Sequence[str],
    preferred_skills: Sequence[str] = (),
    certifications: Sequence[str] = (),
    min_experience: float | None = None,
    domain: str | None = None,
    description: str | None = None,
) -> str:
    parts = [
        f"Role: {title}" if title else "",
        f"Required skills: {', '.join(required_skills)}" if required_skills else "",
        f"Preferred skills: {', '.join(preferred_skills)}" if preferred_skills else "",
        f"Certifications: {', '.join(certifications)}" if certifications else "",
        f"Minimum experience: {min_experience} years" if min_experience is not None else "",
        f"Domain: {domain}" if domain else "",
        description or "",
    ]
    return "\n".join(part for part in parts if part)
