"""Dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import CandidateStatus, ResumeStatus
from app.graph.registry import get_graph
from app.repositories import candidate_repository as repo
from app.schemas.dashboard import (
    ActivityItem,
    DashboardCards,
    DashboardResponse,
    NamedValue,
    TrendPoint,
)
from app.services.audit import actor_label, recent_activity
from app.services.candidates import STATUS_LABELS


def build_dashboard(session: Session) -> DashboardResponse:
    processing = repo.resume_processing_stats(session)
    cards = DashboardCards(
        total_candidates=repo.count_candidates(session),
        uploaded_resumes=processing["total"],
        shortlisted=repo.count_candidates(session, status=CandidateStatus.SHORTLISTED.value),
        rejected=repo.count_candidates(session, status=CandidateStatus.REJECTED.value),
        pending_review=repo.count_candidates(session, status=CandidateStatus.PENDING_REVIEW.value)
        + repo.count_candidates(session, status=CandidateStatus.NEW.value),
        new_uploads_today=repo.new_uploads_today(session),
        processing=processing["processing"],
        failed_resumes=processing["failed"],
        average_experience_years=repo.average_experience(session),
        average_match_score=repo.average_match_score(session),
    )

    top_skills = [
        NamedValue(name=name, value=count, extra=category)
        for name, count, category in repo.top_skills(session, limit=12)
    ]
    technology_distribution = [
        NamedValue(name=name, value=count) for name, count in repo.technology_distribution(session, limit=10)
    ]
    experience_distribution = [
        NamedValue(name=label, value=count) for label, count in repo.experience_distribution(session)
    ]
    status_counts = repo.status_counts(session)
    candidate_status = [
        NamedValue(
            name=STATUS_LABELS.get(CandidateStatus(status), status.replace("_", " ").title())
            if status in {item.value for item in CandidateStatus}
            else status,
            value=count,
        )
        for status, count in sorted(status_counts.items(), key=lambda item: -item[1])
    ]
    hiring_trends = [
        TrendPoint(period=period, uploads=uploads, candidates=candidates, shortlisted=shortlisted, rejected=rejected)
        for period, uploads, candidates, shortlisted, rejected in repo.hiring_trends(session, months=6)
    ]

    activity = [
        ActivityItem(
            id=entry.id,
            action=entry.action,
            actor=actor_label(entry),
            description=entry.description,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            created_at=entry.created_at,
            status=entry.status,
        )
        for entry in recent_activity(session, limit=15)
    ]

    recent_uploads = [
        {
            "resume_id": resume.id,
            "filename": resume.original_filename,
            "status": resume.status,
            "candidate_id": resume.candidate_id,
            "candidate_name": resume.candidate.full_name if resume.candidate else None,
            "uploaded_by": resume.uploaded_by.full_name if resume.uploaded_by else None,
            "created_at": resume.created_at.isoformat(),
            "parse_duration_ms": resume.parse_duration_ms,
            "error": resume.parse_error,
        }
        for resume in repo.recent_uploads(session, limit=8)
    ]

    graph_stats = get_graph().stats()
    return DashboardResponse(
        cards=cards,
        top_skills=top_skills,
        technology_distribution=technology_distribution,
        experience_distribution=experience_distribution,
        candidate_status=candidate_status,
        hiring_trends=hiring_trends,
        top_companies=[NamedValue(name=name, value=count) for name, count in repo.top_companies(session, limit=8)],
        top_certifications=[
            NamedValue(name=name, value=count) for name, count in repo.top_certifications(session, limit=8)
        ],
        recent_activity=activity,
        recent_uploads=recent_uploads,
        ai_recommendations=_recommendations(session),
        graph=graph_stats.as_dict(),
        generated_at=datetime.now(UTC),
    )


def _recommendations(session: Session) -> list[dict]:
    """Lightweight, explainable nudges shown on the dashboard."""
    recommendations: list[dict] = []

    for run in repo.recent_match_runs(session, limit=2):
        for result in run.results[:3]:
            recommendations.append(
                {
                    "type": "top_match",
                    "title": f"{result.candidate.full_name} scored {round(result.overall_score)}% for {run.title}",
                    "detail": (result.explanation or "")[:220] or None,
                    "candidate_id": result.candidate_id,
                    "score": result.overall_score,
                    "recommendation": result.recommendation,
                    "created_at": run.created_at.isoformat(),
                }
            )

    for candidate in repo.stale_candidates(session, days=14, limit=4):
        recommendations.append(
            {
                "type": "needs_review",
                "title": f"{candidate.full_name} has been waiting for review",
                "detail": f"Uploaded {candidate.created_at:%d %b %Y}, still in '{candidate.status}'.",
                "candidate_id": candidate.id,
                "score": candidate.last_match_score,
                "created_at": candidate.updated_at.isoformat(),
            }
        )

    failed = repo.count_resumes(session, status=ResumeStatus.FAILED.value)
    if failed:
        recommendations.append(
            {
                "type": "action_required",
                "title": f"{failed} resume(s) failed to parse",
                "detail": "Open Resume Upload to review the errors and re-upload or enable OCR.",
                "score": None,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    coverage = repo.taxonomy_coverage(session)
    if coverage and coverage < 80:
        recommendations.append(
            {
                "type": "taxonomy",
                "title": f"Only {coverage}% of extracted skills map to the taxonomy",
                "detail": "Add the unmapped skills or their synonyms to the Skills CSV to improve matching.",
                "score": coverage,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    return recommendations[:8]
