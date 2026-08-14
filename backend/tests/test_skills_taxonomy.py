"""Skills CSV import + taxonomy normalization tests."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.skill import Skill, SkillSynonym
from app.services.skills_import import import_skills_csv
from app.services.taxonomy import get_taxonomy


def test_csv_is_imported_at_startup(client, db_session: Session) -> None:
    total = db_session.scalar(select(func.count(Skill.id))) or 0
    assert total >= 50, "skills.csv should be loaded during application startup"
    assert (db_session.scalar(select(func.count(SkillSynonym.id))) or 0) > 0


def test_import_is_idempotent(client, db_session: Session) -> None:
    before = db_session.scalar(select(func.count(Skill.id))) or 0
    report = import_skills_csv(db_session, settings.skills_csv)
    after = db_session.scalar(select(func.count(Skill.id))) or 0

    assert after == before
    assert report.skills_created == 0
    assert report.skills_updated >= 1
    assert report.rows_read == after or report.rows_read >= report.skills_updated


def test_resolve_exact_and_synonym(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)

    exact = taxonomy.resolve("Python")
    assert exact is not None
    assert exact.skill.name == "Python"
    assert exact.match_type == "exact"

    synonym = taxonomy.resolve("React.js")
    assert synonym is not None
    assert synonym.skill.name.lower().startswith("react")
    assert synonym.confidence >= 0.9


def test_resolve_is_case_and_punctuation_insensitive(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    for phrase in ("postgresql", "PostgreSQL", "  POSTGRESQL  "):
        match = taxonomy.resolve(phrase)
        assert match is not None and match.skill.name == "PostgreSQL"


def test_resolve_typo_uses_fuzzy_matching(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    match = taxonomy.resolve("Kubernetess")
    assert match is not None
    assert match.skill.name == "Kubernetes"
    assert match.match_type == "fuzzy"
    assert match.confidence < 1.0


def test_unknown_phrase_does_not_resolve(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    assert taxonomy.resolve("Underwater Basket Weaving") is None


def test_scan_text_finds_multiple_skills(client, db_session: Session, resume_text: str) -> None:
    taxonomy = get_taxonomy(db_session)
    found = {match.skill.name for match in taxonomy.scan_text(resume_text)}
    assert {"Python", "FastAPI", "PostgreSQL", "Docker"} <= found
    assert all(match.evidence for match in taxonomy.scan_text(resume_text))


def test_expand_traverses_related_skills(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    python = taxonomy.resolve("Python")
    assert python is not None

    expanded = taxonomy.expand(python.skill.id, depth=1)
    names = {item.skill.name for item in expanded}
    assert names, "Python should be connected to related skills from the CSV"
    assert any(name in names for name in ("Django", "Flask", "FastAPI", "Pandas"))
    assert all(0 < item.weight <= 1 for item in expanded)


def test_equivalent_ids_are_symmetric_for_related_skills(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    python = taxonomy.resolve("Python")
    django = taxonomy.resolve("Django")
    assert python and django
    assert django.skill.id in taxonomy.equivalent_ids(python.skill.id)
    assert python.skill.id in taxonomy.equivalent_ids(django.skill.id)


def test_categories_are_populated(client, db_session: Session) -> None:
    taxonomy = get_taxonomy(db_session)
    categories = taxonomy.categories()
    assert len(categories) >= 5
    assert all(nodes for nodes in categories.values())
