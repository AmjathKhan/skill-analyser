"""Resume upload, retrieval and reprocessing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, rate_limit, require_permission
from app.core.config import settings
from app.core.constants import AuditAction, ResumeStatus
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import session_scope
from app.models.resume import Resume
from app.models.user import User
from app.schemas.candidate import ResumeDetail, ResumeSummary, UploadedResumeResult, UploadResponse
from app.schemas.common import MessageResponse, Page, PageMeta
from app.services import resume_processing, storage
from app.services.audit import record_audit
from app.services.candidates import to_resume_summary

logger = get_logger(__name__)

router = APIRouter(tags=["Resumes"])

UploadPermission = Annotated[User, Depends(require_permission("resume:upload"))]
ReadPermission = Annotated[User, Depends(require_permission("resume:read"))]

MAX_FILES_PER_REQUEST = 25


def _process_in_background(resume_id: int, actor_id: int | None) -> None:
    """Runs after the response is sent, in its own session."""
    with session_scope() as session:
        resume_processing.process_resume(session, resume_id, actor_id=actor_id)


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("upload", limit=120, window=60))],
)
def upload_resumes(
    session: DbSession,
    actor: UploadPermission,
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="PDF, DOC or DOCX resumes")],
    allow_duplicates: bool = Query(False, description="Store the file even if an identical one exists"),
    wait: bool = Query(False, description="Process synchronously and return parsing results"),
) -> UploadResponse:
    """Upload one or more resumes. Parsing runs asynchronously unless ``wait=true``."""
    if not files:
        raise ValidationAppError("No files were provided")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise ValidationAppError(f"At most {MAX_FILES_PER_REQUEST} files can be uploaded in one request")

    response = UploadResponse(processed_inline=wait or not settings.use_celery)
    to_process: list[int] = []

    for upload in files:
        filename = upload.filename or "resume"
        try:
            data = upload.file.read()
            resume, duplicate = resume_processing.create_resume(
                session,
                data=data,
                filename=filename,
                uploaded_by_id=actor.id,
                allow_duplicate=allow_duplicates,
            )
            if duplicate is not None:
                response.duplicates += 1
                response.results.append(
                    UploadedResumeResult(
                        filename=filename,
                        resume_id=resume.id,
                        resume_uuid=resume.uuid,
                        candidate_id=duplicate.candidate_id,
                        status=resume.status,
                        is_duplicate=True,
                        duplicate_of_resume_id=duplicate.id,
                        message="Identical file already uploaded - skipped parsing",
                    )
                )
                continue

            response.uploaded += 1
            to_process.append(resume.id)
            response.results.append(
                UploadedResumeResult(
                    filename=filename,
                    resume_id=resume.id,
                    resume_uuid=resume.uuid,
                    status=resume.status,
                    message="Uploaded",
                )
            )
        except Exception as exc:
            logger.warning("upload failed for %s: %s", filename, exc)
            response.failed += 1
            response.results.append(
                UploadedResumeResult(filename=filename, status=ResumeStatus.FAILED.value, error=str(exc))
            )
        finally:
            upload.file.close()

    session.flush()

    if to_process:
        if wait:
            for resume_id in to_process:
                result = resume_processing.process_resume(session, resume_id, actor_id=actor.id)
                for item in response.results:
                    if item.resume_id == resume_id:
                        item.status = result.status
                        item.candidate_id = result.candidate_id
                        item.processing = result.as_dict()
                        item.error = result.error
        elif settings.use_celery:
            from app.workers.tasks import process_resume_task

            for resume_id in to_process:
                task = process_resume_task.delay(resume_id, actor.id)
                queued_resume = session.get(Resume, resume_id)
                if queued_resume is not None:
                    queued_resume.task_id = task.id
                for item in response.results:
                    if item.resume_id == resume_id:
                        item.task_id = task.id
                        item.status = ResumeStatus.QUEUED.value
            response.queued = len(to_process)
        else:
            for resume_id in to_process:
                background_tasks.add_task(_process_in_background, resume_id, actor.id)
            response.queued = len(to_process)

    return response


@router.get("/resumes", response_model=Page[ResumeSummary])
def list_resumes(
    session: DbSession,
    _: ReadPermission,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by processing status"),
    candidate_id: int | None = None,
) -> Page[ResumeSummary]:
    filters = []
    if status:
        filters.append(Resume.status == status)
    if candidate_id:
        filters.append(Resume.candidate_id == candidate_id)

    total = session.scalar(select(func.count(Resume.id)).where(*filters)) or 0
    rows = session.scalars(
        select(Resume)
        .options(selectinload(Resume.uploaded_by), selectinload(Resume.candidate))
        .where(*filters)
        .order_by(Resume.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[ResumeSummary](
        items=[to_resume_summary(resume) for resume in rows],
        meta=PageMeta.build(page=page, page_size=page_size, total=total),
    )


def _require_resume(session, resume_id: int) -> Resume:
    resume = session.get(Resume, resume_id)
    if resume is None:
        raise NotFoundError(f"Resume {resume_id} not found")
    return resume


@router.get("/resume/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: int, session: DbSession, _: ReadPermission, include_text: bool = True) -> ResumeDetail:
    resume = _require_resume(session, resume_id)
    summary = to_resume_summary(resume).model_dump()
    return ResumeDetail(
        **summary,
        raw_text=resume.raw_text if include_text else None,
        parsed_data=resume.parsed_data,
    )


@router.get("/resume/{resume_id}/download")
def download_resume(resume_id: int, session: DbSession, _: ReadPermission, inline: bool = False) -> Response:
    """Stream the original file. ``inline=true`` powers the in-app resume viewer."""
    resume = _require_resume(session, resume_id)
    try:
        data = storage.read_resume(resume.storage_path, encrypted=resume.is_encrypted)
    except FileNotFoundError as exc:
        raise NotFoundError("The stored file is no longer available") from exc

    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
    }
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=media_types.get(resume.extension, "application/octet-stream"),
        headers={
            "Content-Disposition": f'{disposition}; filename="{resume.original_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/resume/{resume_id}/reprocess", response_model=dict)
def reprocess_resume(resume_id: int, session: DbSession, actor: UploadPermission) -> dict:
    resume = _require_resume(session, resume_id)
    if resume.status == ResumeStatus.DUPLICATE.value:
        raise ValidationAppError("Duplicate resumes are not reprocessed; upload with allow_duplicates=true instead")
    result = resume_processing.process_resume(session, resume.id, actor_id=actor.id)
    return result.as_dict()


@router.get("/resume/{resume_id}/status", response_model=dict)
def resume_status(resume_id: int, session: DbSession, _: ReadPermission) -> dict:
    resume = _require_resume(session, resume_id)
    return {
        "resume_id": resume.id,
        "status": resume.status,
        "candidate_id": resume.candidate_id,
        "task_id": resume.task_id,
        "error": resume.parse_error,
        "is_processing": resume.is_processing,
        "parse_duration_ms": resume.parse_duration_ms,
    }


@router.delete("/resume/{resume_id}", response_model=MessageResponse)
def delete_resume(resume_id: int, session: DbSession, actor: CurrentUser) -> MessageResponse:
    resume = _require_resume(session, resume_id)
    if not actor.is_admin and resume.uploaded_by_id != actor.id:
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError("You can only delete resumes you uploaded")

    if not resume.duplicate_of_id:
        storage.delete_resume(resume.storage_path)
    record_audit(
        session,
        action=AuditAction.RESUME_DELETE,
        user_id=actor.id,
        actor_email=actor.email,
        entity_type="resume",
        entity_id=resume.id,
        description=f"Deleted resume '{resume.original_filename}'",
    )
    session.delete(resume)
    return MessageResponse(message="Resume deleted")
