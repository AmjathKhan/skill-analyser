"""Secure resume file storage: validation, checksums and optional encryption."""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import FileTooLargeError, UnsupportedFileError, ValidationAppError
from app.core.logging import get_logger

logger = get_logger(__name__)

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class StoredFile:
    stored_filename: str
    path: Path
    relative_path: str
    checksum: str
    size: int
    extension: str
    encrypted: bool


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    name = _UNSAFE_NAME_RE.sub("_", name).strip("._") or "resume"
    return name[:180]


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_resume_extension(data: bytes) -> str | None:
    """Detect PDF / DOCX / DOC from content so a wrong or missing extension still parses."""
    if not data:
        return None
    if b"%PDF" in data[:1024]:
        return ".pdf"
    if data.startswith(b"PK\x03\x04") and _zip_looks_like_docx(data):
        return ".docx"
    if data.startswith(b"\xd0\xcf\x11\xe0") or data.lstrip().startswith(b"{\\rtf"):
        return ".doc"
    return None


def _zip_looks_like_docx(data: bytes) -> bool:
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
        return "word/document.xml" in names or any(name.startswith("word/") for name in names)
    except Exception:
        return b"word/" in data[:16384] or b"[Content_Types].xml" in data[:4096]


def _matches_named_type(extension: str, data: bytes) -> bool:
    if extension == ".pdf":
        return b"%PDF" in data[:1024]
    if extension == ".docx":
        return data.startswith(b"PK\x03\x04")
    if extension == ".doc":
        return (
            data.startswith(b"\xd0\xcf\x11\xe0")
            or data.startswith(b"PK\x03\x04")
            or data.lstrip().startswith(b"{\\rtf")
        )
    return True


def validate_upload(filename: str, data: bytes) -> str:
    """Validate extension, size and magic bytes. Returns the lowercase extension."""
    if not data:
        raise ValidationAppError("Uploaded file is empty")
    if len(data) > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            f"File exceeds the {settings.max_upload_size_mb} MB limit "
            f"({round(len(data) / 1024 / 1024, 2)} MB received)"
        )

    named = Path(sanitize_filename(filename)).suffix.lower()
    sniffed = sniff_resume_extension(data)

    if named in settings.upload_extensions:
        if named in {".txt", ".md"}:
            return named
        if sniffed == named or (sniffed is None and _matches_named_type(named, data)):
            return named
        if sniffed and sniffed in settings.upload_extensions:
            logger.info("resume %s is named %s but content is %s", filename, named, sniffed)
            return sniffed
        raise UnsupportedFileError(f"File content does not look like a valid {named} document")

    if sniffed and sniffed in settings.upload_extensions:
        return sniffed

    raise UnsupportedFileError(
        f"Unsupported file type '{named or 'unknown'}'. "
        f"Allowed: {', '.join(sorted(settings.upload_extensions))}"
    )


def _fernet():
    if not settings.file_encryption_enabled:
        return None
    if not settings.file_encryption_key:
        logger.warning("FILE_ENCRYPTION_ENABLED is true but FILE_ENCRYPTION_KEY is empty - storing plaintext")
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(settings.file_encryption_key.encode("utf-8"))
    except Exception as exc:
        logger.error("invalid FILE_ENCRYPTION_KEY (%s) - storing plaintext", exc.__class__.__name__)
        return None


def save_resume(data: bytes, original_filename: str) -> StoredFile:
    extension = validate_upload(original_filename, data)
    checksum = compute_checksum(data)

    now = datetime.now(UTC)
    folder = settings.resume_storage_path / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{now:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:10]}{extension}"
    path = folder / stored_filename

    cipher = _fernet()
    payload = cipher.encrypt(data) if cipher else data
    if cipher:
        path = path.with_suffix(path.suffix + ".enc")
        stored_filename = path.name
    path.write_bytes(payload)

    relative = path.relative_to(settings.storage_path).as_posix()
    logger.info("stored resume %s (%s bytes, encrypted=%s)", stored_filename, len(data), bool(cipher))
    return StoredFile(
        stored_filename=stored_filename,
        path=path,
        relative_path=relative,
        checksum=checksum,
        size=len(data),
        extension=extension,
        encrypted=bool(cipher),
    )


def resolve_path(relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    if not path.is_absolute():
        path = settings.storage_path / path
    resolved = path.resolve()
    root = settings.storage_path.resolve()
    if not str(resolved).startswith(str(root)):
        raise ValidationAppError("Resolved storage path escapes the storage directory")
    return resolved


def read_resume(relative_path: str, *, encrypted: bool) -> bytes:
    path = resolve_path(relative_path)
    if not path.exists():
        raise FileNotFoundError(f"Stored resume not found: {relative_path}")
    data = path.read_bytes()
    if not encrypted:
        return data
    cipher = _fernet()
    if cipher is None:
        raise ValidationAppError("File is encrypted but no valid encryption key is configured")
    from cryptography.fernet import InvalidToken

    try:
        return cipher.decrypt(data)
    except InvalidToken as exc:
        raise ValidationAppError("Could not decrypt the stored resume (key mismatch)") from exc


def delete_resume(relative_path: str) -> bool:
    try:
        path = resolve_path(relative_path)
    except ValidationAppError:
        return False
    if path.exists():
        path.unlink()
        return True
    return False


def materialize_for_parsing(relative_path: str, *, encrypted: bool, extension: str) -> tuple[Path, bool]:
    """Return a readable path for the parser; decrypts into a temp file if needed."""
    if not encrypted:
        return resolve_path(relative_path), False
    import tempfile

    data = read_resume(relative_path, encrypted=True)
    # The caller parses the file after this returns, so it must outlive the handle.
    with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as handle:
        handle.write(data)
        temp_path = handle.name
    return Path(temp_path), True
