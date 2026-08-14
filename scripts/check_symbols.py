"""Developer helper: assert that cross-module symbols referenced by the API exist."""

from __future__ import annotations

import pathlib
import sys

CHECKS: dict[str, list[str]] = {
    "backend/app/db/session.py": ["def check_database", "def ensure_extensions", "def session_scope"],
    "backend/app/ai/vector_store.py": ["def get_vector_store", "def stats", "def rebuild_index"],
    "backend/app/services/reports.py": ["def export_report", "def export_candidates_csv", "def build_report"],
    "backend/app/services/taxonomy.py": ["def all_skills", "def categories", "def get("],
    "backend/app/core/constants.py": ["REPORT_EXPORT"],
    "backend/app/schemas/common.py": ["class HealthResponse"],
    "backend/app/core/config.py": [
        "auto_import_skills",
        "skills_csv",
        "match_weights",
        "upload_extensions",
        "file_encryption_enabled",
        "use_celery",
        "api_prefix",
        "app_version",
        "cors_origins",
        "ensure_directories",
        "sqlalchemy_database_uri",
        "class Environment",
        "spacy_model",
        "enable_ocr",
        "max_upload_size_mb",
        "vector_backend",
        "embedding_backend",
        "llm_backend",
        "llm_model",
    ],
    "backend/app/graph/base.py": ["def as_dict", "healthy"],
    "backend/app/core/logging.py": ["request_id_ctx", "def get_logger", "def configure_logging"],
    "backend/app/services/graph_service.py": ["def ensure_hydrated"],
    "backend/app/schemas/dashboard.py": ["class ReportResponse"],
    "backend/app/services/resume_processing.py": ["def embed_skill_taxonomy", "def generate_candidate_embeddings"],
    "backend/app/models/candidate.py": ["latest_resume"],
    "backend/app/schemas/skill.py": [
        "class SkillTaxonomyRead",
        "class SkillImportResponse",
        "class JobRequirementCreate",
        "class JobRequirementRead",
        "class SkillCategoryRead",
    ],
}


def main() -> int:
    failures = 0
    root = pathlib.Path(__file__).resolve().parents[1]
    for relative, names in CHECKS.items():
        path = root / relative
        if not path.exists():
            print(f"{relative}: FILE MISSING")
            failures += 1
            continue
        text = path.read_text(encoding="utf-8")
        missing = [name for name in names if name not in text]
        status = "ok" if not missing else f"MISSING {missing}"
        if missing:
            failures += 1
        print(f"{relative}: {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
