"""Shared enumerations used across models, schemas and services."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    HR_ADMIN = "hr_admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"

    @property
    def label(self) -> str:
        return {
            UserRole.HR_ADMIN: "HR Admin",
            UserRole.RECRUITER: "Recruiter",
            UserRole.HIRING_MANAGER: "Hiring Manager",
        }[self]


#: Coarse-grained permissions mapped to roles (RBAC).
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.HR_ADMIN: {
        "user:manage",
        "candidate:read",
        "candidate:write",
        "candidate:delete",
        "resume:upload",
        "resume:read",
        "graph:build",
        "graph:read",
        "match:run",
        "search:run",
        "report:read",
        "settings:manage",
        "audit:read",
    },
    UserRole.RECRUITER: {
        "candidate:read",
        "candidate:write",
        "resume:upload",
        "resume:read",
        "graph:read",
        "graph:build",
        "match:run",
        "search:run",
        "report:read",
    },
    UserRole.HIRING_MANAGER: {
        "candidate:read",
        "resume:read",
        "graph:read",
        "match:run",
        "search:run",
        "report:read",
    },
}


class CandidateStatus(str, Enum):
    NEW = "new"
    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    SHORTLISTED = "shortlisted"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


class ResumeStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PARSING = "parsing"
    PARSED = "parsed"
    EMBEDDING = "embedding"
    GRAPH_SYNC = "graph_sync"
    COMPLETED = "completed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class ProficiencyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SkillSource(str, Enum):
    RESUME_SKILLS_SECTION = "resume_skills_section"
    RESUME_EXPERIENCE = "resume_experience"
    RESUME_PROJECT = "resume_project"
    RESUME_CERTIFICATION = "resume_certification"
    SEMANTIC_INFERENCE = "semantic_inference"
    GRAPH_INFERENCE = "graph_inference"
    MANUAL = "manual"


class EmbeddingKind(str, Enum):
    RESUME = "resume"
    RESUME_CHUNK = "resume_chunk"
    SKILL = "skill"
    PROJECT = "project"
    CERTIFICATION = "certification"
    JOB_REQUIREMENT = "job_requirement"


class Recommendation(str, Enum):
    HIGHLY_RECOMMENDED = "Highly Recommended"
    RECOMMENDED = "Recommended"
    CONSIDER = "Consider"
    NOT_RECOMMENDED = "Not Recommended"


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET = "password_reset"
    RESUME_UPLOAD = "resume_upload"
    RESUME_DELETE = "resume_delete"
    CANDIDATE_UPDATE = "candidate_update"
    CANDIDATE_DELETE = "candidate_delete"
    CANDIDATE_STATUS_CHANGE = "candidate_status_change"
    SKILL_MATCH = "skill_match"
    SEARCH = "search"
    GRAPH_BUILD = "graph_build"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    REPORT_EXPORT = "report_export"
    NOTE_CREATE = "note_create"


#: Node labels of the knowledge graph.
class NodeLabel(str, Enum):
    CANDIDATE = "Candidate"
    SKILL = "Skill"
    TECHNOLOGY = "Technology"
    COMPANY = "Company"
    CERTIFICATION = "Certification"
    PROJECT = "Project"
    EDUCATION = "Education"
    JOB_ROLE = "JobRole"
    DEPARTMENT = "Department"
    CATEGORY = "Category"


#: Relationship types of the knowledge graph.
class RelationType(str, Enum):
    HAS_SKILL = "HAS_SKILL"
    BELONGS_TO = "BELONGS_TO"
    RELATED_TO = "RELATED_TO"
    PARENT_OF = "PARENT_OF"
    WORKED_AT = "WORKED_AT"
    COMPLETED = "COMPLETED"
    HOLDS = "HOLDS"
    STUDIED_AT = "STUDIED_AT"
    REQUIRED_FOR = "REQUIRED_FOR"
    DEPENDS_ON = "DEPENDS_ON"
    USES = "USES"
    PART_OF = "PART_OF"
    USED_SKILL = "USED_SKILL"


EXPERIENCE_LEVEL_YEARS: dict[str, tuple[float, float]] = {
    "beginner": (0.0, 2.0),
    "junior": (0.0, 2.0),
    "intermediate": (2.0, 5.0),
    "mid": (2.0, 5.0),
    "advanced": (5.0, 8.0),
    "senior": (5.0, 10.0),
    "expert": (8.0, 40.0),
    "lead": (8.0, 40.0),
}
