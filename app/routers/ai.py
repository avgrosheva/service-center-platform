"""
AI endpoints (Milestone 18).

This module is only ever imported/registered when `settings.ai_enabled`
is true — see `main.py`'s `create_app`. With `AI_ENABLED=false` (the
default), FastAPI never sees these routes at all, so a request to any
`/ai/*` path 404s exactly like any other undefined path, never 403 —
"the app is fully functional with every AI feature disabled" is proven by
the routes not existing, not by an access check turning requests away.

Role gate: owner/dispatcher/technician for every route — same
three-role set job_items.py uses, since nothing here writes financial or
administrative state (AI never writes to Job/AdditionalWorkItem/Payment
at all, per the hard rule in ai_service.py and workers/ai_tasks.py's
docstrings). Job-scoped endpoints (summary, suggest-additional-work)
still enforce the usual per-job access rule via ai_service.py: a
technician only on their own assigned job (403 otherwise), any
owner/dispatcher on any job in the org, and a cross-org job_id is 404.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.ai_task import AITaskRead, QueryRequest, VoiceNoteRequest
from app.services import ai_service
from app.workers import ai_tasks

router = APIRouter(prefix="/ai", tags=["ai"])

_can_use_ai = require_role(UserRole.OWNER, UserRole.DISPATCHER, UserRole.TECHNICIAN)


@router.post("/voice-note", response_model=AITaskRead, status_code=status.HTTP_201_CREATED)
async def submit_voice_note(
    data: VoiceNoteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_use_ai),
):
    task = await ai_service.create_voice_note_task(db, current_user.organization_id, data.transcript)
    background_tasks.add_task(ai_tasks.process_ai_task, task.id)
    return task


@router.post("/jobs/{job_id}/summary", response_model=AITaskRead, status_code=status.HTTP_201_CREATED)
async def request_job_summary(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_use_ai),
):
    try:
        task = await ai_service.create_job_summary_task(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except ai_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ai_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    background_tasks.add_task(ai_tasks.process_ai_task, task.id)
    return task


@router.post(
    "/jobs/{job_id}/suggest-additional-work", response_model=AITaskRead, status_code=status.HTTP_201_CREATED
)
async def request_additional_work_suggestion(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_use_ai),
):
    try:
        task = await ai_service.create_additional_work_suggestion_task(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except ai_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ai_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    background_tasks.add_task(ai_tasks.process_ai_task, task.id)
    return task


@router.post("/query", response_model=AITaskRead, status_code=status.HTTP_201_CREATED)
async def submit_query(
    data: QueryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_use_ai),
):
    task = await ai_service.create_query_task(db, current_user.organization_id, data.query)
    background_tasks.add_task(ai_tasks.process_ai_task, task.id)
    return task


@router.get("/tasks/{task_id}", response_model=AITaskRead)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_use_ai),
):
    try:
        return await ai_service.get_task(db, current_user.organization_id, task_id)
    except ai_service.AITaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
