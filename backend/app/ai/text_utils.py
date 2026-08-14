"""Text normalization helpers shared by the parser, taxonomy and graph layers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

#: Characters kept when collapsing a skill name: "C++" and "C#" must survive.
_KEEP_CHARS = set("+#")

_WHITESPACE_RE = re.compile(r"\s+")
_BULLET_RE = re.compile(r"^[\s]*[\u2022\u25cf\u25aa\u2023\u2043\-\*\u00b7o]\s+", re.MULTILINE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_EMAIL_RE = re.compile(r"[\w!#$%&'*+/=?^_`{|}~.-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"https?://[^\s,;)\]]+|www\.[^\s,;)\]]+", re.IGNORECASE)
_STOPWORDS = {
    "and", "or", "the", "with", "for", "of", "in", "on", "at", "to", "a", "an", "using",
    "experience", "years", "year", "skills", "skill", "knowledge", "strong", "good",
    "excellent", "working", "hands", "expertise", "proficient", "familiar",
}


def clean_text(text: str) -> str:
    """Normalize unicode, bullets and whitespace while preserving line structure."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = _BULLET_RE.sub("", text)
    text = "\n".join(_WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return _MULTI_NEWLINE_RE.sub("\n\n", text).strip()


def normalize_key(value: str) -> str:
    """Collapse a term to a comparison key: ``Node.js`` -> ``nodejs``, ``C++`` -> ``c++``."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).lower().strip()
    value = value.replace("&", "and")
    return "".join(ch for ch in value if ch.isalnum() or ch in _KEEP_CHARS)


def normalize_phrase(value: str) -> str:
    """Lowercase and squeeze whitespace but keep word boundaries (for display/search)."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[^\w+#./\- ]", " ", value)
    return _WHITESPACE_RE.sub(" ", value).strip()


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "-", value.lower())
    value = re.sub(r"[\s_]+", "-", value).strip("-")
    return re.sub(r"-{2,}", "-", value) or "item"


def title_case(value: str) -> str:
    small = {"of", "and", "the", "in", "for", "a", "an", "to", "on", "at"}
    words = value.strip().split()
    out: list[str] = []
    for index, word in enumerate(words):
        if word.isupper() and len(word) <= 5:
            out.append(word)
        elif index and word.lower() in small:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def similarity(left: str, right: str) -> float:
    """Character-level similarity of two normalized terms in [0, 1]."""
    a, b = normalize_key(left), normalize_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def tokenize(text: str, *, drop_stopwords: bool = True, min_length: int = 2) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
    result = []
    for token in tokens:
        token = token.strip(".")
        if len(token) < min_length:
            continue
        if drop_stopwords and token in _STOPWORDS:
            continue
        result.append(token)
    return result


def ngrams(tokens: list[str], max_n: int = 4) -> list[str]:
    out: list[str] = []
    for size in range(1, max_n + 1):
        for index in range(len(tokens) - size + 1):
            out.append(" ".join(tokens[index : index + size]))
    return out


def extract_emails(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).rstrip(".") for match in _EMAIL_RE.finditer(text)))


def extract_urls(text: str) -> list[str]:
    urls = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;")
        if not url.lower().startswith("http"):
            url = f"https://{url}"
        urls.append(url)
    return list(dict.fromkeys(urls))


def truncate(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "\u2026"


def split_list_field(value: str | None, separators: str = ";|,") -> list[str]:
    """Split a CSV cell that may contain ``a;b|c,d`` into clean parts."""
    if not value:
        return []
    pattern = f"[{re.escape(separators)}]"
    return [part.strip() for part in re.split(pattern, str(value)) if part and part.strip()]


def _split_oversized(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Break paragraphs longer than ``chunk_size`` on word boundaries, keeping an overlap."""
    step = max(chunk_size - overlap, chunk_size // 2, 1)
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            pieces.append(paragraph)
            continue
        words = paragraph.split()
        current: list[str] = []
        current_len = 0
        for word in words:
            if current and current_len + len(word) + 1 > chunk_size:
                pieces.append(" ".join(current))
                carried: list[str] = []
                carried_len = 0
                for previous in reversed(current):
                    if carried_len + len(previous) + 1 > chunk_size - step:
                        break
                    carried.insert(0, previous)
                    carried_len += len(previous) + 1
                current, current_len = carried, carried_len
            current.append(word)
            current_len += len(word) + 1
        if current:
            pieces.append(" ".join(current))
    return pieces


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    """Split text for RAG. Uses LangChain's splitter when available, else paragraphs."""
    text = (text or "").strip()
    if not text:
        return []
    try:  # pragma: no cover - exercised only with AI extras installed
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        split = [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
        if split:
            return split
    except Exception:
        pass

    chunks: list[str] = []
    buffer: list[str] = []
    length = 0
    for paragraph in _split_oversized(re.split(r"\n{2,}", text), chunk_size, overlap):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if length + len(paragraph) > chunk_size and buffer:
            chunks.append("\n\n".join(buffer))
            tail = buffer[-1][-overlap:] if overlap else ""
            buffer = [tail] if tail else []
            length = len(tail)
        buffer.append(paragraph)
        length += len(paragraph)
    if buffer:
        chunks.append("\n\n".join(buffer))
    return [chunk.strip() for chunk in chunks if chunk.strip()]
