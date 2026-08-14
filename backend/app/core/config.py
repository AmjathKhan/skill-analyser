"""Application settings, loaded from environment variables / .env."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Environment(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"
    test = "test"


class EmbeddingBackend(str, Enum):
    hash = "hash"
    sentence_transformers = "sentence-transformers"


class VectorBackend(str, Enum):
    pgvector = "pgvector"
    faiss = "faiss"
    numpy = "numpy"


class GraphBackend(str, Enum):
    networkx = "networkx"
    neo4j = "neo4j"


class LLMBackend(str, Enum):
    template = "template"
    openai = "openai"


def _csv_to_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "AI Skill Analyser"
    app_version: str = "1.0.0"
    environment: Environment = Environment.development
    debug: bool = True
    api_prefix: str = "/api"
    backend_cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    # --- Security ---
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 30
    session_idle_timeout_minutes: int = 30
    password_reset_token_expire_minutes: int = 30
    bcrypt_rounds: int = 12
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 300
    rate_limit_window_seconds: int = 60
    login_rate_limit_requests: int = 10
    login_rate_limit_window_seconds: int = 300

    # --- Database ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "skill_analyser"
    postgres_user: str = "skill_analyser"
    postgres_password: str = "skill_analyser"
    database_url: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    use_celery: bool = False

    # --- Storage ---
    storage_dir: str = str(BACKEND_ROOT / "storage")
    max_upload_size_mb: int = 15
    allowed_upload_extensions: str = ".pdf,.doc,.docx,.txt"
    file_encryption_enabled: bool = False
    file_encryption_key: str | None = None

    # --- Skills knowledge base ---
    skills_csv_path: str = str(BACKEND_ROOT / "data" / "skills.csv")
    auto_import_skills: bool = True

    # --- AI / NLP ---
    embedding_backend: EmbeddingBackend = EmbeddingBackend.hash
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    spacy_model: str = "en_core_web_sm"
    enable_ocr: bool = False
    tesseract_cmd: str | None = None

    # --- Vector search ---
    vector_backend: VectorBackend = VectorBackend.numpy
    vector_search_top_k: int = 50

    # --- Graph ---
    graph_backend: GraphBackend = GraphBackend.networkx
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    neo4j_database: str = "neo4j"

    # --- LLM ---
    llm_backend: LLMBackend = LLMBackend.template
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    llm_temperature: float = 0.2
    llm_max_tokens: int = 800

    # --- Matching weights ---
    match_weight_skill: float = 0.40
    match_weight_semantic: float = 0.20
    match_weight_experience: float = 0.20
    match_weight_certification: float = 0.10
    match_weight_project: float = 0.10

    # --- Frontend (optional SPA served by FastAPI) ---
    frontend_dist: str | None = None

    # --- Bootstrap admin ---
    first_superuser_email: str = "admin@skillanalyser.ai"
    first_superuser_password: str = "Admin@12345"
    first_superuser_name: str = "HR Administrator"

    @field_validator("secret_key")
    @classmethod
    def _validate_secret(cls, value: str) -> str:
        if len(value) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return _csv_to_list(self.backend_cors_origins)

    @property
    def upload_extensions(self) -> set[str]:
        return {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in _csv_to_list(self.allowed_upload_extensions)}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_database_uri.startswith("sqlite")

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return path

    @property
    def resume_storage_path(self) -> Path:
        return self.storage_path / "resumes"

    @property
    def skills_csv(self) -> Path:
        path = Path(self.skills_csv_path)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return path

    @property
    def match_weights(self) -> dict[str, float]:
        return {
            "skill": self.match_weight_skill,
            "semantic": self.match_weight_semantic,
            "experience": self.match_weight_experience,
            "certification": self.match_weight_certification,
            "project": self.match_weight_project,
        }

    def ensure_directories(self) -> None:
        self.resume_storage_path.mkdir(parents=True, exist_ok=True)
        (self.storage_path / "exports").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

# Tests and scripts may point at a different database; expose a helper to reload.
def reload_settings() -> Settings:
    global settings
    get_settings.cache_clear()
    settings = get_settings()
    return settings


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
