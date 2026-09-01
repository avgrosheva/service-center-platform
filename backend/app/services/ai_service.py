"""
AI task management business logic (Milestone 18) — synchronous, DB-only:
validates access, creates a `pending` ai_tasks row, and reads task status
back. Never calls the Anthropic API itself and never touches Job/
AdditionalWorkItem/Payment — that split mirrors job_items_service.py
(sync validation + row creation) vs. workers/document_tasks.py (the
actual external call + result write-back), applied here as
ai_service.py vs. workers/ai_tasks.py.

Job-scoped tasks (summary, additional-work suggestion) reuse
job_service.get_scoped_job / check_technician_access directly — same
access rule as every other job sub-resource: owner/dispatcher see and act
on every job in the org, a technician only their own assigned job. A
cross-org job_id is 404 (get_scoped_job never finds it); a same-org job
that isn't the technician's is 403.

Voice-note and free-text-query tasks aren't job-scoped, so they only need
the caller's organization_id — any authenticated member of the org
(owner/dispatcher/technician) can create one, gated at the router by the
same three-role dependency the rest of the job-facing endpoints use.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_task import AITask, AITaskType
from app.models.user import User
from app.services import job_service


class AIServiceError(Exception):
    """Base class for AI-service failures the router maps to HTTP status codes."""


class JobNotFoundError(AIServiceError):
    pass


class ForbiddenJobAccessError(AIServiceError):
    pass


class AITaskNotFoundError(AIServiceError):
    pass


async def create_voice_note_task(db: AsyncSession, organization_id: uuid.UUID, transcript: str) -> AITask:
    task = AITask(
        organization_id=organization_id,
        job_id=None,
        task_type=AITaskType.VOICE_TRANSCRIPTION,
        input_ref=transcript,
    )
    db.add(task)
    await db.flush()
    return task


async def create_job_summary_task(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> AITask:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user)
    task = AITask(
        organization_id=organization_id,
        job_id=job.id,
        task_type=AITaskType.SUMMARY,
        input_ref=str(job.id),
    )
    db.add(task)
    await db.flush()
    return task


async def create_additional_work_suggestion_task(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> AITask:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user)
    task = AITask(
        organization_id=organization_id,
        job_id=job.id,
        task_type=AITaskType.ADDITIONAL_WORK_SUGGESTION,
        input_ref=str(job.id),
    )
    db.add(task)
    await db.flush()
    return task


async def create_query_task(db: AsyncSession, organization_id: uuid.UUID, query: str) -> AITask:
    task = AITask(
        organization_id=organization_id,
        job_id=None,
        task_type=AITaskType.QA_QUERY,
        input_ref=query,
    )
    db.add(task)
    await db.flush()
    return task


async def get_task(db: AsyncSession, organization_id: uuid.UUID, task_id: uuid.UUID) -> AITask:
    result = await db.execute(
        select(AITask).where(AITask.id == task_id, AITask.organization_id == organization_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise AITaskNotFoundError(f"No AI task {task_id} in this organization")
    return task


async def _get_job_for_access(db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, requesting_user: User):
    job = await job_service.get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")
    try:
        job_service.check_technician_access(job, requesting_user)
    except job_service.ForbiddenJobAccessError as exc:
        raise ForbiddenJobAccessError(str(exc)) from exc
    return job
