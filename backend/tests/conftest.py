"""Shared pytest fixtures.

The suite runs entirely offline against SQLite with the deterministic hash embedder
and the in-process NetworkX graph, so no PostgreSQL / Neo4j / Redis is required.
Environment variables are set *before* the application is imported because
``app.core.config.settings`` is built at import time.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = TEST_ROOT.parent
_TMP_STORAGE = Path(tempfile.mkdtemp(prefix="skill-analyser-tests-"))
_DB_PATH = _TMP_STORAGE / "test.db"

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "SECRET_KEY": "test-secret-key-that-is-long-enough",
        "DATABASE_URL": f"sqlite:///{_DB_PATH.as_posix()}",
        "STORAGE_DIR": str(_TMP_STORAGE / "storage"),
        "RATE_LIMIT_ENABLED": "false",
        "USE_CELERY": "false",
        "EMBEDDING_BACKEND": "hash",
        "VECTOR_BACKEND": "numpy",
        "GRAPH_BACKEND": "networkx",
        "LLM_BACKEND": "template",
        "AUTO_IMPORT_SKILLS": "true",
        "FILE_ENCRYPTION_ENABLED": "false",
        "BCRYPT_ROUNDS": "4",
        "ALLOWED_UPLOAD_EXTENSIONS": ".pdf,.doc,.docx,.txt",
    }
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.constants import UserRole  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F403 - register all tables

SAMPLE_RESUMES = BACKEND_ROOT / "data" / "sample_resumes"

USERS = {
    "admin": ("hr.admin@example.com", "HR Admin", "AdminPass#1", UserRole.HR_ADMIN),
    "recruiter": ("recruiter@example.com", "Rita Recruiter", "RecruitPass#1", UserRole.RECRUITER),
    "manager": ("manager@example.com", "Max Manager", "ManagerPass#1", UserRole.HIRING_MANAGER),
}


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    settings.ensure_directories()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    shutil.rmtree(_TMP_STORAGE, ignore_errors=True)


@pytest.fixture(scope="session")
def client(_database: None) -> Iterator[TestClient]:
    """Client with lifespan executed: imports the Skills CSV and hydrates the graph."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="session")
def seeded_users(client: TestClient) -> dict[str, dict[str, str]]:
    from app.services.auth import create_user, get_user_by_email

    created: dict[str, dict[str, str]] = {}
    session = SessionLocal()
    try:
        for key, (email, name, password, role) in USERS.items():
            if get_user_by_email(session, email) is None:
                create_user(session, email=email, full_name=name, password=password, role=role)
            created[key] = {"email": email, "password": password, "role": role.value}
        session.commit()
    finally:
        session.close()
    return created


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(client: TestClient, seeded_users: dict[str, dict[str, str]]) -> dict[str, str]:
    token = _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def recruiter_headers(client: TestClient, seeded_users: dict[str, dict[str, str]]) -> dict[str, str]:
    token = _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def manager_headers(client: TestClient, seeded_users: dict[str, dict[str, str]]) -> dict[str, str]:
    token = _login(client, seeded_users["manager"]["email"], seeded_users["manager"]["password"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def uploaded_candidates(client: TestClient, admin_headers: dict[str, str]) -> list[dict]:
    """Upload every sample resume once and process it synchronously."""
    files = [
        ("files", (path.name, path.read_bytes(), "text/plain"))
        for path in sorted(SAMPLE_RESUMES.glob("*.txt"))
    ]
    assert files, "sample resumes are missing"
    response = client.post("/api/upload?wait=true", files=files, headers=admin_headers)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["uploaded"] >= 3, payload
    return payload["results"]


@pytest.fixture()
def resume_text() -> str:
    return (SAMPLE_RESUMES / "priya_sharma_fullstack.txt").read_text(encoding="utf-8")
