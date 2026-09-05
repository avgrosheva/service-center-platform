"""
Job sub-resource endpoints — photos (Milestone 10), materials
(Milestone 11), additional work (Milestone 12), and documents
(Milestone 14), per the Technical Blueprint's project structure (one
routers/job_items.py file for every job sub-resource).

Role gate matches routers/jobs.py's `_can_view_or_act_on_jobs` for
read/create actions: owner/dispatcher read and write every job's
sub-resources; a technician is scoped to only the job(s) assigned to
them, enforced in job_items_service.py (403, not 404, on a same-org job
that isn't theirs — see routers/jobs.py's docstring for why; a cross-org
job_id is 404, same as everywhere else). Approving/rejecting/billing
additional work is the one action gated more strictly, to owner/dispatcher
only regardless of job assignment — flagging it is a field action, but
deciding on it is a dispatch/office decision per the Technical Blueprint's
role table.

Triggering document generation is the one endpoint here that touches
`BackgroundTasks`: it validates access synchronously (so a bad/forbidden
job_id 404s/403s immediately, same as everything else), then schedules
`workers/document_tasks.generate_document` and returns 202 immediately —
per the roadmap, no Document row exists yet at that point, so there's
nothing meaningful to return in the body.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.additional_work_item import (
    AdditionalWorkItemCreate,
    AdditionalWorkItemRead,
    AdditionalWorkItemStatusUpdate,
)
from app.schemas.document import DocumentGenerateRequest, DocumentRead
from app.schemas.material_item import MaterialItemCreate, MaterialItemRead, MaterialItemUpdate
from app.schemas.photo import PhotoCreate, PhotoRead, PhotoUploadURLRequest, PhotoUploadURLResponse
from app.services import job_items_service
from app.workers import document_tasks

router = APIRouter(prefix="/jobs/{job_id}", tags=["job-items"])

_can_manage_job_items = require_role(UserRole.OWNER, UserRole.DISPATCHER, UserRole.TECHNICIAN)
_can_approve_additional_work = require_role(UserRole.OWNER, UserRole.DISPATCHER)


@router.post("/photos/upload-url", response_model=PhotoUploadURLResponse)
async def get_photo_upload_url(
    job_id: uuid.UUID,
    data: PhotoUploadURLRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        upload_url, s3_key = await job_items_service.generate_photo_upload_url(
            db, current_user.organization_id, job_id, data.content_type, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return PhotoUploadURLResponse(upload_url=upload_url, s3_key=s3_key)


@router.post("/photos", response_model=PhotoRead, status_code=status.HTTP_201_CREATED)
async def create_photo(
    job_id: uuid.UUID,
    data: PhotoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.create_photo(
            db, current_user.organization_id, job_id, data.s3_key, data.tag, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except job_items_service.InvalidPhotoKeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/photos", response_model=list[PhotoRead])
async def list_photos(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.list_photos(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/materials", response_model=MaterialItemRead, status_code=status.HTTP_201_CREATED)
async def add_material(
    job_id: uuid.UUID,
    data: MaterialItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.add_material(
            db, current_user.organization_id, job_id, data, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/materials", response_model=list[MaterialItemRead])
async def list_materials(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.list_materials(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/materials/{material_id}", response_model=MaterialItemRead)
async def update_material(
    job_id: uuid.UUID,
    material_id: uuid.UUID,
    data: MaterialItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.update_material(
            db, current_user.organization_id, job_id, material_id, data, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except job_items_service.MaterialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_material(
    job_id: uuid.UUID,
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        await job_items_service.remove_material(
            db, current_user.organization_id, job_id, material_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except job_items_service.MaterialNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/additional-work", response_model=AdditionalWorkItemRead, status_code=status.HTTP_201_CREATED)
async def flag_additional_work(
    job_id: uuid.UUID,
    data: AdditionalWorkItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.flag_additional_work(
            db, current_user.organization_id, job_id, data, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/additional-work", response_model=list[AdditionalWorkItemRead])
async def list_additional_work(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.list_additional_work(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/additional-work/{item_id}", response_model=AdditionalWorkItemRead)
async def update_additional_work_status(
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    data: AdditionalWorkItemStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_approve_additional_work),
):
    try:
        return await job_items_service.update_additional_work_status(
            db, current_user.organization_id, job_id, item_id, data.status, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.AdditionalWorkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.InvalidAdditionalWorkStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def trigger_document_generation(
    job_id: uuid.UUID,
    data: DocumentGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        await job_items_service.ensure_job_access(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    background_tasks.add_task(
        document_tasks.generate_document, job_id, current_user.organization_id, data.type, current_user.id
    )
    return {"status": "accepted", "type": data.type.value}


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_job_items),
):
    try:
        return await job_items_service.list_documents(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_items_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_items_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
