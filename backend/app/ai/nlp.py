"""Lazy spaCy loader. Every caller must tolerate ``None`` (rule-based fallback)."""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_nlp: Any | None = None
_loaded = False
_lock = threading.Lock()


def get_nlp() -> Any | None:
    """Return a loaded spaCy pipeline, or None when spaCy/the model is unavailable."""
    global _nlp, _loaded
    if _loaded:
        return _nlp
    with _lock:
        if _loaded:
            return _nlp
        _loaded = True
        try:
            import spacy

            try:
                _nlp = spacy.load(settings.spacy_model, exclude=["lemmatizer", "textcat"])
                logger.info("loaded spaCy model %s", settings.spacy_model)
            except OSError:
                logger.warning(
                    "spaCy model %s not installed - run `python -m spacy download %s`. "
                    "Falling back to rule-based extraction.",
                    settings.spacy_model,
                    settings.spacy_model,
                )
                _nlp = None
        except ImportError:
            logger.info("spaCy not installed - using rule-based extraction")
            _nlp = None
    return _nlp


def entities(text: str, labels: set[str] | None = None, *, max_chars: int = 20000) -> list[tuple[str, str]]:
    """Return ``(text, label)`` named entities, or an empty list without spaCy."""
    nlp = get_nlp()
    if nlp is None or not text:
        return []
    doc = nlp(text[:max_chars])
    return [(ent.text.strip(), ent.label_) for ent in doc.ents if labels is None or ent.label_ in labels]


def noun_phrases(text: str, *, max_chars: int = 20000) -> list[str]:
    nlp = get_nlp()
    if nlp is None or not text:
        return []
    doc = nlp(text[:max_chars])
    return [chunk.text.strip() for chunk in getattr(doc, "noun_chunks", [])]


def is_available() -> bool:
    return get_nlp() is not None
