"""Skills CSV import utility.

Loads the authoritative skill taxonomy (skill id, name, category, parent skill,
related skills, technology stack, job role, experience level, synonyms and
description) into PostgreSQL, normalizing names, synonyms and categories.

Idempotent: re-running updates existing rows instead of duplicating them.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.text_utils import normalize_key, slugify, split_list_field, title_case
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.models.skill import JobRole, Skill, SkillCategory, SkillRelation, SkillSynonym
from app.services.taxonomy import invalidate_taxonomy

logger = get_logger(__name__)

#: Accepted spellings for each logical CSV column.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "skill_id": ("skill_id", "skillid", "id", "code"),
    "skill_name": ("skill_name", "skillname", "name", "skill"),
    "category": ("category", "skill_category", "categoryname", "category_name"),
    "parent_skill": ("parent_skill", "parentskill", "parent"),
    "related_skills": ("related_skills", "relatedskills", "related"),
    "technology_stack": ("technology_stack", "technologystack", "tech_stack", "stack"),
    "job_role": ("job_role", "jobrole", "job_roles", "roles", "role"),
    "experience_level": ("experience_level", "experiencelevel", "level"),
    "skill_synonyms": ("skill_synonyms", "synonyms", "skillsynonyms", "aliases", "alias"),
    "skill_description": ("skill_description", "description", "skilldescription", "definition"),
}

NON_TECHNICAL_CATEGORIES = {"soft skill", "soft skills", "methodology", "process", "language", "behavioural"}


@dataclass(slots=True)
class ImportReport:
    source: str = ""
    rows_read: int = 0
    skills_created: int = 0
    skills_updated: int = 0
    categories_created: int = 0
    synonyms_created: int = 0
    relations_created: int = 0
    job_roles_created: int = 0
    parents_linked: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "rows_read": self.rows_read,
            "skills_created": self.skills_created,
            "skills_updated": self.skills_updated,
            "categories_created": self.categories_created,
            "synonyms_created": self.synonyms_created,
            "relations_created": self.relations_created,
            "job_roles_created": self.job_roles_created,
            "parents_linked": self.parents_linked,
            "skipped": self.skipped[:25],
            "skipped_count": len(self.skipped),
        }


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_").lstrip("\ufeff")


def _build_column_map(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {_normalize_header(name): name for name in fieldnames if name}
    mapping: dict[str, str] = {}
    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[logical] = normalized[alias]
                break
    return mapping


def _cell(row: dict[str, str], column_map: dict[str, str], logical: str) -> str:
    source = column_map.get(logical)
    if not source:
        return ""
    return (row.get(source) or "").strip()


def _unique_slug(name: str, taken: set[str]) -> str:
    """``C`` and ``C#`` both slugify to ``c``; keep the column unique deterministically."""
    base = slugify(name)
    if base not in taken:
        taken.add(base)
        return base
    suffix = normalize_key(name).replace("+", "plus").replace("#", "sharp").replace(".", "dot")
    candidate = slugify(f"{base}-{suffix}") if suffix and suffix != base else f"{base}-2"
    counter = 2
    while candidate in taken:
        candidate = f"{base}-{counter}"
        counter += 1
    taken.add(candidate)
    return candidate


def import_skills_csv(session: Session, csv_path: str | Path, *, refresh_taxonomy: bool = True) -> ImportReport:
    path = Path(csv_path)
    if not path.exists():
        raise ValidationAppError(f"Skills CSV not found at {path}")

    report = ImportReport(source=str(path))

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationAppError("Skills CSV appears to be empty")
        column_map = _build_column_map(reader.fieldnames)
        if "skill_name" not in column_map:
            raise ValidationAppError(
                "Skills CSV must contain a skill name column (skill_name / name / skill)"
            )
        rows = list(reader)

    categories = {category.normalized_name: category for category in session.scalars(select(SkillCategory))}
    job_roles = {role.normalized_name: role for role in session.scalars(select(JobRole))}
    skills_by_key: dict[str, Skill] = {
        skill.normalized_name: skill for skill in session.scalars(select(Skill))
    }
    slugs_taken: set[str] = {skill.slug for skill in skills_by_key.values() if skill.slug}

    # ---------------------------------------------------------------- pass 1
    pending_parents: list[tuple[Skill, str]] = []
    pending_relations: list[tuple[Skill, str]] = []

    for index, row in enumerate(rows, start=2):
        report.rows_read += 1
        name = _cell(row, column_map, "skill_name")
        if not name:
            report.skipped.append(f"line {index}: missing skill name")
            continue

        normalized = normalize_key(name)
        if not normalized:
            report.skipped.append(f"line {index}: skill name '{name}' normalizes to empty")
            continue

        category_name = _cell(row, column_map, "category")
        category = None
        if category_name:
            category_key = normalize_key(category_name)
            category = categories.get(category_key)
            if category is None:
                category = SkillCategory(name=title_case(category_name), normalized_name=category_key)
                session.add(category)
                session.flush()
                categories[category_key] = category
                report.categories_created += 1

        skill = skills_by_key.get(normalized)
        created = skill is None
        if skill is None:
            skill = Skill(name=name.strip(), normalized_name=normalized, slug=_unique_slug(name, slugs_taken))
            session.add(skill)

        skill.name = name.strip()
        skill.normalized_name = normalized
        skill.slug = skill.slug or _unique_slug(name, slugs_taken)
        skill.external_id = _cell(row, column_map, "skill_id") or skill.external_id
        skill.category_id = category.id if category else skill.category_id
        skill.technology_stack = _cell(row, column_map, "technology_stack") or None
        skill.experience_level = (_cell(row, column_map, "experience_level") or "").lower() or None
        skill.description = _cell(row, column_map, "skill_description") or None
        skill.is_technical = (category_name or "").strip().lower() not in NON_TECHNICAL_CATEGORIES
        session.flush()

        skills_by_key[normalized] = skill
        if created:
            report.skills_created += 1
        else:
            report.skills_updated += 1

        # --- synonyms ---
        existing_synonyms = {
            synonym.normalized_synonym for synonym in session.scalars(
                select(SkillSynonym).where(SkillSynonym.skill_id == skill.id)
            )
        }
        for synonym in split_list_field(_cell(row, column_map, "skill_synonyms")):
            synonym_key = normalize_key(synonym)
            if not synonym_key or synonym_key == normalized or synonym_key in existing_synonyms:
                continue
            session.add(
                SkillSynonym(
                    skill_id=skill.id,
                    synonym=synonym.strip(),
                    normalized_synonym=synonym_key,
                    source="csv",
                )
            )
            existing_synonyms.add(synonym_key)
            report.synonyms_created += 1

        # --- job roles ---
        for role_name in split_list_field(_cell(row, column_map, "job_role")):
            role_key = normalize_key(role_name)
            if not role_key:
                continue
            role = job_roles.get(role_key)
            if role is None:
                role = JobRole(name=title_case(role_name), normalized_name=role_key)
                session.add(role)
                session.flush()
                job_roles[role_key] = role
                report.job_roles_created += 1
            if role not in skill.job_roles:
                skill.job_roles.append(role)

        parent_name = _cell(row, column_map, "parent_skill")
        if parent_name:
            pending_parents.append((skill, parent_name))
        related = _cell(row, column_map, "related_skills")
        if related:
            pending_relations.append((skill, related))

    session.flush()

    # ---------------------------------------------------------------- pass 2
    for skill, parent_name in pending_parents:
        parent = skills_by_key.get(normalize_key(parent_name))
        if parent is None or parent.id == skill.id:
            report.skipped.append(f"unknown parent skill '{parent_name}' for '{skill.name}'")
            continue
        if skill.parent_skill_id != parent.id:
            skill.parent_skill_id = parent.id
            report.parents_linked += 1

    existing_relations = {
        (relation.source_skill_id, relation.target_skill_id, relation.relation_type)
        for relation in session.scalars(select(SkillRelation))
    }
    for skill, related_cell in pending_relations:
        for related_name in split_list_field(related_cell):
            target = skills_by_key.get(normalize_key(related_name))
            if target is None:
                report.skipped.append(f"unknown related skill '{related_name}' for '{skill.name}'")
                continue
            if target.id == skill.id:
                continue
            key = (skill.id, target.id, "RELATED_TO")
            if key in existing_relations:
                continue
            session.add(
                SkillRelation(
                    source_skill_id=skill.id,
                    target_skill_id=target.id,
                    relation_type="RELATED_TO",
                    weight=0.6,
                )
            )
            existing_relations.add(key)
            report.relations_created += 1

    session.flush()
    if refresh_taxonomy:
        invalidate_taxonomy()

    logger.info(
        "skills import complete: %s created, %s updated, %s synonyms, %s relations",
        report.skills_created,
        report.skills_updated,
        report.synonyms_created,
        report.relations_created,
    )
    return report


def skills_table_is_empty(session: Session) -> bool:
    return session.scalar(select(Skill.id).limit(1)) is None
