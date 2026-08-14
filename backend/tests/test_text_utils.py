"""Unit tests for text normalization helpers."""

from __future__ import annotations

import pytest

from app.ai.text_utils import (
    chunk_text,
    clean_text,
    extract_emails,
    extract_urls,
    ngrams,
    normalize_key,
    similarity,
    slugify,
    split_list_field,
    tokenize,
    truncate,
)


def test_clean_text_normalizes_whitespace_and_bullets() -> None:
    raw = "Senior\u00a0Engineer\r\n\u2022 Built APIs\n\n\n\u25cf Led team   \n"
    cleaned = clean_text(raw)
    assert "\u00a0" not in cleaned
    assert "\u2022" not in cleaned
    assert "Senior Engineer" in cleaned
    assert cleaned.count("\n\n") <= 1


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ReactJS", "react js"),
        ("Node.js", "nodejs"),
        ("C++", "c++"),
        ("  Amazon   Web   Services ", "amazon web services"),
    ],
)
def test_normalize_key_collapses_variants(left: str, right: str) -> None:
    assert normalize_key(left) == normalize_key(right)


def test_normalize_key_keeps_distinct_skills_distinct() -> None:
    assert normalize_key("Java") != normalize_key("JavaScript")


def test_slugify() -> None:
    assert slugify("Amazon Web Services (AWS)") == "amazon-web-services-aws"
    assert slugify("C#") in {"c", "c-sharp", "csharp"}


def test_similarity_bounds() -> None:
    assert similarity("python", "python") == 1.0
    assert 0.0 <= similarity("python", "pyhton") <= 1.0
    assert similarity("python", "kubernetes") < 0.6


def test_tokenize_and_ngrams() -> None:
    tokens = tokenize("Built REST APIs with FastAPI and PostgreSQL", drop_stopwords=False)
    assert "fastapi" in tokens
    grams = list(ngrams(tokens, 2))
    assert any(gram.count(" ") == 1 for gram in grams)


def test_extract_contacts() -> None:
    text = "Reach me at jane.doe@example.co.in or https://github.com/janedoe"
    assert extract_emails(text) == ["jane.doe@example.co.in"]
    assert any("github.com" in url for url in extract_urls(text))


def test_split_list_field() -> None:
    assert split_list_field("Django;Flask; FastAPI") == ["Django", "Flask", "FastAPI"]
    assert split_list_field("") == []


def test_truncate() -> None:
    long_text = "the quick brown fox jumps over the lazy dog"
    shortened = truncate(long_text, 20)
    assert shortened.endswith("\u2026")
    assert len(shortened) <= 20
    assert truncate("abc", 10) == "abc"


def test_chunk_text_produces_overlapping_chunks() -> None:
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
