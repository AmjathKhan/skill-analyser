"""Seed baseline and demo data.

    python -m scripts.seed --skills            # import the Skills CSV taxonomy
    python -m scripts.seed --users             # bootstrap admin + demo accounts
    python -m scripts.seed --demo              # ingest sample resumes end to end
    python -m scripts.seed --skills --users --demo --graph
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.constants import UserRole
from app.core.logging import configure_logging, get_logger
from app.db.session import check_database, ensure_extensions, session_scope
from app.models.job import JobRequirement
from app.models.user import User

logger = get_logger("seed")

SAMPLE_RESUME_DIR = Path(__file__).resolve().parents[1] / "data" / "sample_resumes"

DEMO_USERS: list[tuple[str, str, str, UserRole]] = [
    ("recruiter@skillanalyser.ai", "Riya Recruiter", "Recruiter#2024", UserRole.RECRUITER),
    ("manager@skillanalyser.ai", "Manish Manager", "Manager#2024", UserRole.HIRING_MANAGER),
]

DEMO_JOBS = [
    {
        "title": "Senior Full Stack Engineer",
        "department": "Engineering",
        "location": "Bengaluru",
        "description": (
            "Build cloud-native products end to end. You will own FastAPI services backed by "
            "PostgreSQL and a ReactJS + TypeScript front end deployed to AWS with Docker."
        ),
        "min_experience_years": 5.0,
        "required": ["Python", "FastAPI", "ReactJS", "PostgreSQL", "Docker"],
        "preferred": ["AWS", "Kubernetes", "TypeScript"],
        "certifications": ["AWS Certified Solutions Architect"],
        "domain": "Product Engineering",
    },
    {
        "title": "Machine Learning Engineer - NLP",
        "department": "AI",
        "location": "Remote",
        "description": (
            "Own retrieval augmented generation systems: embeddings, vector search, knowledge "
            "graphs and explainable ranking served from FastAPI."
        ),
        "min_experience_years": 3.0,
        "required": ["Python", "PyTorch", "Hugging Face Transformers", "NLP", "FastAPI"],
        "preferred": ["Neo4j", "FAISS", "LangChain"],
        "certifications": ["AWS Certified Machine Learning"],
        "domain": "Applied AI",
    },
]


def seed_skills() -> None:
    from app.services.resume_processing import embed_skill_taxonomy
    from app.services.skills_import import import_skills_csv, skills_table_is_empty
    from app.services.taxonomy import get_taxonomy

    csv_path = settings.skills_csv
    if not csv_path.exists():
        logger.error("skills CSV not found at %s", csv_path)
        return

    with session_scope() as session:
        was_empty = skills_table_is_empty(session)
        report = import_skills_csv(session, csv_path)
        get_taxonomy(session, refresh=True)
        embedded = embed_skill_taxonomy(session)
        logger.info(
            "skills %s: %s rows -> +%s new, %s updated, %s synonyms, %s relations, %s embeddings",
            "imported" if was_empty else "refreshed",
            report.rows_read,
            report.skills_created,
            report.skills_updated,
            report.synonyms_created,
            report.relations_created,
            embedded,
        )


def seed_users() -> None:
    from app.services.auth import create_user, get_user_by_email

    with session_scope() as session:
        admin = get_user_by_email(session, settings.first_superuser_email)
        if admin is None:
            admin = create_user(
                session,
                email=settings.first_superuser_email,
                full_name=settings.first_superuser_name,
                password=settings.first_superuser_password,
                role=UserRole.HR_ADMIN,
                department="Human Resources",
            )
            logger.info("created HR admin %s", admin.email)
        else:
            logger.info("HR admin %s already exists", admin.email)

        for email, name, password, role in DEMO_USERS:
            if get_user_by_email(session, email) is None:
                create_user(
                    session,
                    email=email,
                    full_name=name,
                    password=password,
                    role=role,
                    department="Talent Acquisition",
                )
                logger.info("created %s (%s)", email, role.value)


def seed_jobs() -> None:
    with session_scope() as session:
        admin = session.scalar(select(User).where(User.role == UserRole.HR_ADMIN.value).limit(1))
        for spec in DEMO_JOBS:
            exists = session.scalar(select(JobRequirement).where(JobRequirement.title == spec["title"]))
            if exists is not None:
                continue
            session.add(
                JobRequirement(
                    title=str(spec["title"]),
                    department=str(spec["department"]),
                    location=str(spec["location"]),
                    description=str(spec["description"]),
                    min_experience_years=float(spec["min_experience_years"]),
                    required_skills=[
                        {"skill": skill, "weight": 1.0, "mandatory": False} for skill in spec["required"]
                    ],
                    preferred_skills=[{"skill": skill, "weight": 0.5, "mandatory": False} for skill in spec["preferred"]],
                    preferred_certifications=list(spec["certifications"]),
                    preferred_domain=str(spec["domain"]),
                    created_by_id=admin.id if admin else None,
                )
            )
            logger.info("created job requirement %s", spec["title"])


def seed_demo_resumes(*, prefer_pdf: bool = True) -> None:
    from app.services.resume_processing import create_resume, process_resume

    if not SAMPLE_RESUME_DIR.exists():
        logger.error("sample resume folder missing: %s", SAMPLE_RESUME_DIR)
        return

    files: list[Path] = []
    for source in sorted(SAMPLE_RESUME_DIR.glob("*.txt")):
        pdf = source.with_suffix(".pdf")
        docx = source.with_suffix(".docx")
        if prefer_pdf and pdf.exists():
            files.append(pdf)
        elif docx.exists():
            files.append(docx)
        else:
            files.append(source)

    with session_scope() as session:
        admin = session.scalar(select(User).where(User.role == UserRole.HR_ADMIN.value).limit(1))
        actor_id = admin.id if admin else None

        for path in files:
            data = path.read_bytes()
            resume, duplicate = create_resume(
                session,
                data=data,
                filename=path.name,
                uploaded_by_id=actor_id,
            )
            session.flush()
            if duplicate is not None:
                logger.info("%s already ingested (duplicate of resume %s)", path.name, duplicate.id)
                continue
            result = process_resume(session, resume.id, actor_id=actor_id)
            logger.info(
                "processed %s -> candidate=%s skills=%s status=%s%s",
                path.name,
                result.candidate_id,
                result.skills_normalized,
                result.status,
                f" error={result.error}" if result.error else "",
            )


def seed_graph() -> None:
    from app.graph.builder import KnowledgeGraphBuilder

    with session_scope() as session:
        result = KnowledgeGraphBuilder(session).build_full(clear=True)
        logger.info("knowledge graph built: %s", result.as_dict())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the AI Skill Analyser database")
    parser.add_argument("--skills", action="store_true", help="Import the Skills CSV taxonomy")
    parser.add_argument("--users", action="store_true", help="Create admin and demo users")
    parser.add_argument("--jobs", action="store_true", help="Create demo job requirements")
    parser.add_argument("--demo", action="store_true", help="Ingest the sample resumes")
    parser.add_argument("--graph", action="store_true", help="Rebuild the knowledge graph")
    parser.add_argument("--all", action="store_true", help="Everything above")
    args = parser.parse_args(argv)

    configure_logging("INFO")
    if not any([args.skills, args.users, args.jobs, args.demo, args.graph, args.all]):
        parser.print_help()
        return 0

    if not check_database():
        logger.error("cannot reach the database at %s", settings.postgres_host)
        return 2

    settings.ensure_directories()
    ensure_extensions()

    from app.services.skills_import import skills_table_is_empty

    with session_scope() as session:
        taxonomy_missing = skills_table_is_empty(session)

    # Resumes can only be normalized once the taxonomy exists, so pull it in implicitly.
    if args.skills or args.all or ((args.demo or args.graph) and taxonomy_missing):
        seed_skills()
    if args.users or args.all:
        seed_users()
    if args.jobs or args.all:
        seed_jobs()
    if args.demo or args.all:
        seed_demo_resumes()
    if args.graph or args.all or args.demo:
        seed_graph()

    logger.info("seed complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
