"""Initial schema: users, skills taxonomy, candidates, resumes, AI artefacts.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import JSONType

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # pgvector powers VECTOR_BACKEND=pgvector; pg_trgm speeds up ILIKE search.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="recruiter"),
        sa.Column("department", sa.String(128)),
        sa.Column("phone", sa.String(32)),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", TIMESTAMP),
        sa.Column("last_login_at", TIMESTAMP),
        *_timestamps(),
    )
    op.create_index("ix_users_uuid", "users", ["uuid"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_created_at", "users", ["created_at"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("refresh_jti", sa.String(64)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("remember_me", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", TIMESTAMP),
        sa.Column("expires_at", TIMESTAMP),
        *_timestamps(),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_session_id", "user_sessions", ["session_id"], unique=True)
    op.create_index("ix_user_sessions_refresh_jti", "user_sessions", ["refresh_jti"])
    op.create_index("ix_user_sessions_is_revoked", "user_sessions", ["is_revoked"])
    op.create_index("ix_user_sessions_created_at", "user_sessions", ["created_at"])

    # ------------------------------------------------------- skills taxonomy
    op.create_table(
        "skill_categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("normalized_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("color", sa.String(16)),
        *_timestamps(),
    )
    op.create_index("ix_skill_categories_name", "skill_categories", ["name"], unique=True)
    op.create_index("ix_skill_categories_normalized_name", "skill_categories", ["normalized_name"])
    op.create_index("ix_skill_categories_created_at", "skill_categories", ["created_at"])

    op.create_table(
        "job_roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("normalized_name", sa.String(160), nullable=False),
        sa.Column("department", sa.String(128)),
        sa.Column("description", sa.Text),
        *_timestamps(),
    )
    op.create_index("ix_job_roles_name", "job_roles", ["name"], unique=True)
    op.create_index("ix_job_roles_normalized_name", "job_roles", ["normalized_name"])
    op.create_index("ix_job_roles_created_at", "job_roles", ["created_at"])

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("external_id", sa.String(64)),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("normalized_name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("skill_categories.id", ondelete="SET NULL")),
        sa.Column("parent_skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="SET NULL")),
        sa.Column("technology_stack", sa.String(128)),
        sa.Column("experience_level", sa.String(32)),
        sa.Column("description", sa.Text),
        sa.Column("is_technical", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("popularity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extra", JSONType),
        *_timestamps(),
    )
    op.create_index("ix_skills_external_id", "skills", ["external_id"], unique=True)
    op.create_index("ix_skills_name", "skills", ["name"], unique=True)
    op.create_index("ix_skills_slug", "skills", ["slug"], unique=True)
    op.create_index("ix_skills_normalized_name", "skills", ["normalized_name"])
    op.create_index("ix_skills_technology_stack", "skills", ["technology_stack"])
    op.create_index("ix_skills_category_id", "skills", ["category_id"])
    op.create_index("ix_skills_parent_skill_id", "skills", ["parent_skill_id"])
    op.create_index("ix_skills_created_at", "skills", ["created_at"])

    op.create_table(
        "skill_synonyms",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("synonym", sa.String(160), nullable=False),
        sa.Column("normalized_synonym", sa.String(160), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="csv"),
        *_timestamps(),
        sa.UniqueConstraint("skill_id", "normalized_synonym", name="uq_skill_synonym"),
    )
    op.create_index("ix_skill_synonyms_skill_id", "skill_synonyms", ["skill_id"])
    op.create_index("ix_skill_synonyms_normalized_synonym", "skill_synonyms", ["normalized_synonym"])
    op.create_index("ix_skill_synonyms_created_at", "skill_synonyms", ["created_at"])

    op.create_table(
        "skill_relations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False, server_default="RELATED_TO"),
        sa.Column("weight", sa.Float, nullable=False, server_default="0.6"),
        *_timestamps(),
        sa.UniqueConstraint("source_skill_id", "target_skill_id", "relation_type", name="uq_skill_relation"),
    )
    op.create_index("ix_skill_relations_source_skill_id", "skill_relations", ["source_skill_id"])
    op.create_index("ix_skill_relations_target_skill_id", "skill_relations", ["target_skill_id"])
    op.create_index("ix_skill_relations_created_at", "skill_relations", ["created_at"])

    op.create_table(
        "skill_job_roles",
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("job_role_id", sa.Integer, sa.ForeignKey("job_roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("importance", sa.Float, server_default="1.0"),
    )

    # ------------------------------------------------------------- companies
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(128)),
        sa.Column("website", sa.String(255)),
        sa.Column("size", sa.String(64)),
        sa.Column("location", sa.String(255)),
        sa.Column("technologies", JSONType),
        *_timestamps(),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=True)
    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"])
    op.create_index("ix_companies_created_at", "companies", ["created_at"])

    # ------------------------------------------------------------ candidates
    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(64)),
        sa.Column("address", sa.String(512)),
        sa.Column("city", sa.String(128)),
        sa.Column("state", sa.String(128)),
        sa.Column("country", sa.String(128)),
        sa.Column("linkedin_url", sa.String(512)),
        sa.Column("github_url", sa.String(512)),
        sa.Column("portfolio_url", sa.String(512)),
        sa.Column("headline", sa.String(255)),
        sa.Column("current_title", sa.String(255)),
        sa.Column("current_company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("current_company_name", sa.String(255)),
        sa.Column("total_experience_years", sa.Float, nullable=False, server_default="0"),
        sa.Column("relevant_experience_years", sa.Float),
        sa.Column("highest_degree", sa.String(128)),
        sa.Column("notice_period_days", sa.Integer),
        sa.Column("availability", sa.String(64)),
        sa.Column("expected_ctc", sa.String(64)),
        sa.Column("languages", JSONType),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("tags", JSONType),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ai_summary", sa.Text),
        sa.Column("ai_highlights", JSONType),
        sa.Column("last_match_score", sa.Float),
        sa.Column("profile_completeness", sa.Float),
        sa.Column("graph_synced_at", TIMESTAMP),
        *_timestamps(),
    )
    op.create_index("ix_candidates_uuid", "candidates", ["uuid"], unique=True)
    op.create_index("ix_candidates_full_name", "candidates", ["full_name"])
    op.create_index("ix_candidates_email", "candidates", ["email"])
    op.create_index("ix_candidates_phone", "candidates", ["phone"])
    op.create_index("ix_candidates_city", "candidates", ["city"])
    op.create_index("ix_candidates_country", "candidates", ["country"])
    op.create_index("ix_candidates_current_title", "candidates", ["current_title"])
    op.create_index("ix_candidates_current_company_id", "candidates", ["current_company_id"])
    op.create_index("ix_candidates_current_company_name", "candidates", ["current_company_name"])
    op.create_index("ix_candidates_availability", "candidates", ["availability"])
    op.create_index("ix_candidates_status", "candidates", ["status"])
    op.create_index("ix_candidates_owner_id", "candidates", ["owner_id"])
    op.create_index("ix_candidates_is_deleted", "candidates", ["is_deleted"])
    op.create_index("ix_candidates_created_at", "candidates", ["created_at"])
    op.create_index("ix_candidates_status_created", "candidates", ["status", "created_at"])
    op.create_index("ix_candidates_experience", "candidates", ["total_experience_years"])

    # --------------------------------------------------------------- resumes
    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE")),
        sa.Column("uploaded_by_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(128)),
        sa.Column("extension", sa.String(16), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column("task_id", sa.String(64)),
        sa.Column("parse_error", sa.Text),
        sa.Column("duplicate_of_id", sa.Integer, sa.ForeignKey("resumes.id", ondelete="SET NULL")),
        sa.Column("page_count", sa.Integer),
        sa.Column("word_count", sa.Integer),
        sa.Column("ocr_used", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extraction_backend", sa.String(48)),
        sa.Column("raw_text", sa.Text),
        sa.Column("parsed_data", JSONType),
        sa.Column("parse_started_at", TIMESTAMP),
        sa.Column("parse_completed_at", TIMESTAMP),
        sa.Column("parse_duration_ms", sa.Integer),
        *_timestamps(),
    )
    op.create_index("ix_resumes_uuid", "resumes", ["uuid"], unique=True)
    op.create_index("ix_resumes_candidate_id", "resumes", ["candidate_id"])
    op.create_index("ix_resumes_uploaded_by_id", "resumes", ["uploaded_by_id"])
    op.create_index("ix_resumes_checksum", "resumes", ["checksum"])
    op.create_index("ix_resumes_status", "resumes", ["status"])
    op.create_index("ix_resumes_task_id", "resumes", ["task_id"])
    op.create_index("ix_resumes_created_at", "resumes", ["created_at"])

    # ------------------------------------------------- candidate sub-entities
    op.create_table(
        "candidate_skills",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE")),
        sa.Column("raw_text", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("proficiency", sa.String(32), server_default="intermediate"),
        sa.Column("years_experience", sa.Float),
        sa.Column("last_used_year", sa.Integer),
        sa.Column("source", sa.String(48), nullable=False, server_default="resume_skills_section"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.8"),
        sa.Column("evidence", sa.Text),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skill"),
    )
    op.create_index("ix_candidate_skills_candidate_id", "candidate_skills", ["candidate_id"])
    op.create_index("ix_candidate_skills_skill_id", "candidate_skills", ["skill_id"])
    op.create_index("ix_candidate_skills_normalized_name", "candidate_skills", ["normalized_name"])
    op.create_index("ix_candidate_skills_skill", "candidate_skills", ["skill_id", "candidate_id"])
    op.create_index("ix_candidate_skills_created_at", "candidate_skills", ["created_at"])

    op.create_table(
        "educations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("degree", sa.String(255)),
        sa.Column("field_of_study", sa.String(255)),
        sa.Column("institution", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("start_year", sa.Integer),
        sa.Column("graduation_year", sa.Integer),
        sa.Column("grade", sa.String(64)),
        sa.Column("description", sa.Text),
        *_timestamps(),
    )
    op.create_index("ix_educations_candidate_id", "educations", ["candidate_id"])
    op.create_index("ix_educations_degree", "educations", ["degree"])
    op.create_index("ix_educations_institution", "educations", ["institution"])
    op.create_index("ix_educations_graduation_year", "educations", ["graduation_year"])
    op.create_index("ix_educations_created_at", "educations", ["created_at"])

    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("job_title", sa.String(255)),
        sa.Column("employment_type", sa.String(64)),
        sa.Column("location", sa.String(255)),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("duration_months", sa.Integer),
        sa.Column("description", sa.Text),
        sa.Column("technologies", JSONType),
        *_timestamps(),
    )
    op.create_index("ix_experiences_candidate_id", "experiences", ["candidate_id"])
    op.create_index("ix_experiences_company_id", "experiences", ["company_id"])
    op.create_index("ix_experiences_company_name", "experiences", ["company_name"])
    op.create_index("ix_experiences_job_title", "experiences", ["job_title"])
    op.create_index("ix_experiences_created_at", "experiences", ["created_at"])

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("technologies", JSONType),
        sa.Column("url", sa.String(512)),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        *_timestamps(),
    )
    op.create_index("ix_projects_candidate_id", "projects", ["candidate_id"])
    op.create_index("ix_projects_created_at", "projects", ["created_at"])

    op.create_table(
        "certifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("issuer", sa.String(255)),
        sa.Column("credential_id", sa.String(128)),
        sa.Column("issue_date", sa.Date),
        sa.Column("expiry_date", sa.Date),
        sa.Column("url", sa.String(512)),
        *_timestamps(),
    )
    op.create_index("ix_certifications_candidate_id", "certifications", ["candidate_id"])
    op.create_index("ix_certifications_name", "certifications", ["name"])
    op.create_index("ix_certifications_normalized_name", "certifications", ["normalized_name"])
    op.create_index("ix_certifications_issuer", "certifications", ["issuer"])
    op.create_index("ix_certifications_created_at", "certifications", ["created_at"])

    # ------------------------------------------------------ job requirements
    op.create_table(
        "job_requirements",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("department", sa.String(128)),
        sa.Column("location", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("job_role_id", sa.Integer, sa.ForeignKey("job_roles.id", ondelete="SET NULL")),
        sa.Column("min_experience_years", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_experience_years", sa.Float),
        sa.Column("required_skills", JSONType),
        sa.Column("preferred_skills", JSONType),
        sa.Column("preferred_certifications", JSONType),
        sa.Column("preferred_domain", sa.String(128)),
        sa.Column("education_requirement", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
    )
    op.create_index("ix_job_requirements_uuid", "job_requirements", ["uuid"], unique=True)
    op.create_index("ix_job_requirements_title", "job_requirements", ["title"])
    op.create_index("ix_job_requirements_is_active", "job_requirements", ["is_active"])
    op.create_index("ix_job_requirements_created_at", "job_requirements", ["created_at"])

    # -------------------------------------------------- notes and audit logs
    op.create_table(
        "recruiter_notes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("rating", sa.Integer),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_index("ix_recruiter_notes_candidate_id", "recruiter_notes", ["candidate_id"])
    op.create_index("ix_recruiter_notes_author_id", "recruiter_notes", ["author_id"])
    op.create_index("ix_recruiter_notes_created_at", "recruiter_notes", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_email", sa.String(255)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", sa.Integer),
        sa.Column("description", sa.Text),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("meta", JSONType),
        *_timestamps(),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])

    # -------------------------------------------------------- AI / embeddings
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="resume"),
        sa.Column("object_type", sa.String(48), nullable=False),
        sa.Column("object_id", sa.Integer, nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE")),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("dim", sa.Integer, nullable=False),
        sa.Column("vector_json", JSONType, nullable=False),
        sa.Column("text_snippet", sa.Text),
        sa.Column("meta", JSONType),
        *_timestamps(),
        sa.UniqueConstraint("object_type", "object_id", "kind", "chunk_index", name="uq_embedding_object"),
    )
    op.create_index("ix_embeddings_kind", "embeddings", ["kind"])
    op.create_index("ix_embeddings_object_id", "embeddings", ["object_id"])
    op.create_index("ix_embeddings_candidate_id", "embeddings", ["candidate_id"])
    op.create_index("ix_embeddings_kind_object", "embeddings", ["kind", "object_type", "object_id"])
    op.create_index("ix_embeddings_created_at", "embeddings", ["created_at"])

    if bind.dialect.name == "postgresql":
        # Native pgvector column mirrors vector_json when VECTOR_BACKEND=pgvector.
        op.execute("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS vector vector(384)")

    op.create_table(
        "knowledge_graph_metadata",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("backend", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("node_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("node_counts", JSONType),
        sa.Column("relationship_counts", JSONType),
        sa.Column("build_duration_ms", sa.Integer),
        sa.Column("last_build_at", TIMESTAMP),
        sa.Column("triggered_by_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text),
        *_timestamps(),
    )
    op.create_index("ix_knowledge_graph_metadata_created_at", "knowledge_graph_metadata", ["created_at"])

    op.create_table(
        "match_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("job_requirement_id", sa.Integer, sa.ForeignKey("job_requirements.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(255)),
        sa.Column("criteria", JSONType, nullable=False),
        sa.Column("weights", JSONType),
        sa.Column("candidates_evaluated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("top_score", sa.Float),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("graph_backend", sa.String(32)),
        sa.Column("embedding_model", sa.String(160)),
        *_timestamps(),
    )
    op.create_index("ix_match_runs_uuid", "match_runs", ["uuid"], unique=True)
    op.create_index("ix_match_runs_created_by_id", "match_runs", ["created_by_id"])
    op.create_index("ix_match_runs_created_at", "match_runs", ["created_at"])

    op.create_table(
        "match_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_run_id", sa.Integer, sa.ForeignKey("match_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Integer, sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overall_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("skill_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("semantic_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("experience_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("certification_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("project_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("recommendation", sa.String(48)),
        sa.Column("matched_skills", JSONType),
        sa.Column("related_skills", JSONType),
        sa.Column("missing_skills", JSONType),
        sa.Column("score_breakdown", JSONType),
        sa.Column("graph_context", JSONType),
        sa.Column("explanation", sa.Text),
        sa.Column("interview_questions", JSONType),
        sa.Column("learning_recommendations", JSONType),
        *_timestamps(),
    )
    op.create_index("ix_match_results_match_run_id", "match_results", ["match_run_id"])
    op.create_index("ix_match_results_candidate_id", "match_results", ["candidate_id"])
    op.create_index("ix_match_results_run_rank", "match_results", ["match_run_id", "rank"])
    op.create_index("ix_match_results_created_at", "match_results", ["created_at"])


def downgrade() -> None:
    for table in (
        "match_results",
        "match_runs",
        "knowledge_graph_metadata",
        "embeddings",
        "audit_logs",
        "recruiter_notes",
        "job_requirements",
        "certifications",
        "projects",
        "experiences",
        "educations",
        "candidate_skills",
        "resumes",
        "candidates",
        "companies",
        "skill_job_roles",
        "skill_relations",
        "skill_synonyms",
        "skills",
        "job_roles",
        "skill_categories",
        "user_sessions",
        "users",
    ):
        op.drop_table(table)
