"""
Job sub-resource business logic — photos (Milestone 10), materials
(Milestone 11), additional work (Milestone 12), and documents
(Milestone 14), per the Technical Blueprint's project structure, which
groups "photos, materials, additional work, documents" into one services
file mirroring one routers file (`routers/job_items.py`).

Document generation is a partial exception to this module's usual shape:
triggering it is fire-and-forget (a FastAPI `BackgroundTasks` job), and
`BackgroundTasks` is a Starlette/FastAPI type that has no business leaking
into a framework-agnostic service module. So `ensure_job_access` below
does only the validation half (raise on a bad/forbidden job_id) and
returns nothing; the router itself calls `background_tasks.add_task(...)`
once validation passes, and `workers/document_tasks.py` — not this
module — owns the actual generation (its own DB session, its own S3
upload, its own timeline entry), since by design it can't share this
request's session anyway.

Access rule (identical across every sub-resource type, per the Technical
Blueprint's Section 6): only the job's assigned technician, or any
owner/dispatcher in the organization, can read or write a job's
sub-resources. This reuses `job_service.get_scoped_job` and
`job_service.check_technician_access` directly rather than duplicating
tenant/ownership scoping here, since a sub-resource's access rule is
always exactly its parent job's access rule. Additional work's
approve/reject/bill action is the one exception: it's owner/dispatcher
only regardless of job assignment, gated at the router level (a
technician never reaches update_additional_work_status at all), matching
Milestone 9's assign/cancel precedent for actions that are dispatch
decisions rather than field actions.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.additional_work_item import AdditionalWorkItem, AdditionalWorkStatus
from app.models.document import Document
from app.models.job_status_history import JobEventType, JobStatusHistory
from app.models.material_item import MaterialItem
from app.models.photo import Photo, PhotoTag
from app.models.user import User
from app.schemas.additional_work_item import AdditionalWorkItemCreate
from app.schemas.material_item import MaterialItemCreate, MaterialItemUpdate
from app.services import job_service
from app.storage import s3_client

# The additional-work state machine, as a literal lookup table matching
# job_service's own convention. "pending -> approved -> billed, or
# pending -> rejected (terminal). No other transitions allowed" per the
# roadmap.
_ALLOWED_ADDITIONAL_WORK_TRANSITIONS: dict[AdditionalWorkStatus, set[AdditionalWorkStatus]] = {
    AdditionalWorkStatus.PENDING: {AdditionalWorkStatus.APPROVED, AdditionalWorkStatus.REJECTED},
    AdditionalWorkStatus.APPROVED: {AdditionalWorkStatus.BILLED},
    AdditionalWorkStatus.REJECTED: set(),
    AdditionalWorkStatus.BILLED: set(),
}

_EVENT_TYPE_BY_ADDITIONAL_WORK_STATUS: dict[AdditionalWorkStatus, JobEventType] = {
    AdditionalWorkStatus.APPROVED: JobEventType.ADDITIONAL_WORK_APPROVED,
    AdditionalWorkStatus.REJECTED: JobEventType.ADDITIONAL_WORK_REJECTED,
    AdditionalWorkStatus.BILLED: JobEventType.ADDITIONAL_WORK_BILLED,
}

# Bucket key convention per the Technical Blueprint, Section 7:
# {organization_id}/jobs/{job_id}/photos/{uuid}.{ext}. Keys here must match
# schemas.photo.PhotoContentType exactly — that Literal is what rejects
# anything else with a 422 before this function ever runs, so every
# content_type reaching here is guaranteed to have an entry.
_EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}

# Matches exactly what generate_photo_upload_url builds for a given job —
# create_photo checks a submitted s3_key against this rather than trusting
# it outright. Without this, a client could confirm ANY key as a photo on
# a job they can write to (another organization's job photo, a document,
# ...) and _with_view_url would then hand back a valid presigned GET URL
# for it — an IDOR letting an authenticated user read arbitrary objects in
# the shared bucket, not just their own job's. Same fix as
# user_service.py's own _is_own_avatar_key, for the same reason.
_PHOTO_KEY_PATTERN = re.compile(
    r"^(?P<organization_id>[0-9a-f-]{36})/jobs/(?P<job_id>[0-9a-f-]{36})/photos/"
    r"[0-9a-f-]{36}\.(?:jpg|png|webp|heic)$"
)


def _is_own_photo_key(organization_id: uuid.UUID, job_id: uuid.UUID, s3_key: str) -> bool:
    match = _PHOTO_KEY_PATTERN.match(s3_key)
    if match is None:
        return False
    return match["organization_id"] == str(organization_id) and match["job_id"] == str(job_id)


class JobItemsServiceError(Exception):
    """Base class for job-sub-resource failures the router maps to HTTP status codes."""


class JobNotFoundError(JobItemsServiceError):
    pass


class ForbiddenJobAccessError(JobItemsServiceError):
    pass


class InvalidPhotoKeyError(JobItemsServiceError):
    pass


class MaterialNotFoundError(JobItemsServiceError):
    pass


class AdditionalWorkNotFoundError(JobItemsServiceError):
    pass


class InvalidAdditionalWorkStatusTransitionError(JobItemsServiceError):
    pass


async def _get_job_for_access(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
):
    job = await job_service.get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")
    try:
        job_service.check_technician_access(job, requesting_user)
    except job_service.ForbiddenJobAccessError as exc:
        raise ForbiddenJobAccessError(str(exc)) from exc
    return job


async def generate_photo_upload_url(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    content_type: str,
    *,
    requesting_user: User,
) -> tuple[str, str]:
    await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    extension = _EXTENSION_BY_CONTENT_TYPE[content_type]
    key = f"{organization_id}/jobs/{job_id}/photos/{uuid.uuid4()}.{extension}"
    upload_url = s3_client.generate_presigned_upload_url(key, content_type)
    return upload_url, key


async def create_photo(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    s3_key: str,
    tag: PhotoTag | None,
    *,
    requesting_user: User,
) -> Photo:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)
    if not _is_own_photo_key(organization_id, job_id, s3_key):
        raise InvalidPhotoKeyError("This s3_key was not issued for this job's photos")

    photo = Photo(job_id=job.id, uploaded_by_id=requesting_user.id, s3_key=s3_key, tag=tag)
    db.add(photo)

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=JobEventType.PHOTO_ADDED.value,
            note=f"Photo added ({tag.value})" if tag else "Photo added",
        )
    )

    await db.flush()
    await db.refresh(photo)
    return _with_view_url(photo)


async def list_photos(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> list[Photo]:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    result = await db.execute(select(Photo).where(Photo.job_id == job.id).order_by(Photo.created_at))
    return [_with_view_url(photo) for photo in result.scalars().all()]


def _with_view_url(photo: Photo) -> Photo:
    # A transient attribute, not a persisted column — see PhotoRead's own
    # docstring on `view_url`. Generating a presigned URL is pure local
    # signing (no network call), so doing this per-photo on every list
    # call is cheap.
    photo.view_url = s3_client.generate_presigned_download_url(photo.s3_key)
    return photo


async def add_material(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    data: MaterialItemCreate,
    *,
    requesting_user: User,
) -> MaterialItem:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    material = MaterialItem(job_id=job.id, name=data.name, quantity=data.quantity, unit_cost=data.unit_cost)
    db.add(material)

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=JobEventType.MATERIAL_ADDED.value,
            note=f"Material added: {data.name}",
        )
    )

    await db.flush()
    await db.refresh(material)
    return material


async def list_materials(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> list[MaterialItem]:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    result = await db.execute(
        select(MaterialItem).where(MaterialItem.job_id == job.id).order_by(MaterialItem.created_at)
    )
    return list(result.scalars().all())


async def update_material(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    material_id: uuid.UUID,
    data: MaterialItemUpdate,
    *,
    requesting_user: User,
) -> MaterialItem:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)
    material = await _get_scoped_material(db, job.id, material_id)
    if material is None:
        raise MaterialNotFoundError(f"No material {material_id} on this job")

    if data.name is not None:
        material.name = data.name
    if data.quantity is not None:
        material.quantity = data.quantity
    if data.unit_cost is not None:
        material.unit_cost = data.unit_cost

    # A single generic timeline entry per the roadmap's explicit guidance
    # ("edits ... optionally logged, but keep this lightweight — a single
    # generic note entry is enough, not a full audit diff") — no
    # field-by-field before/after diff.
    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=JobEventType.MATERIAL_EDITED.value,
            note=f"Material edited: {material.name}",
        )
    )

    await db.flush()
    await db.refresh(material)
    return material


async def remove_material(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, material_id: uuid.UUID, *, requesting_user: User
) -> None:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)
    material = await _get_scoped_material(db, job.id, material_id)
    if material is None:
        raise MaterialNotFoundError(f"No material {material_id} on this job")

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=JobEventType.MATERIAL_REMOVED.value,
            note=f"Material removed: {material.name}",
        )
    )

    await db.delete(material)
    await db.flush()


async def _get_scoped_material(
    db: AsyncSession, job_id: uuid.UUID, material_id: uuid.UUID
) -> MaterialItem | None:
    result = await db.execute(
        select(MaterialItem).where(MaterialItem.id == material_id, MaterialItem.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def flag_additional_work(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    data: AdditionalWorkItemCreate,
    *,
    requesting_user: User,
) -> AdditionalWorkItem:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    # created_by_id always comes from requesting_user, never client input —
    # this is what guarantees attribution can never be broken regardless of
    # which role (owner, dispatcher, or the assigned technician) flags it.
    item = AdditionalWorkItem(
        organization_id=organization_id,
        job_id=job.id,
        description=data.description,
        price=data.price,
        status=AdditionalWorkStatus.PENDING,
        created_by_id=requesting_user.id,
    )
    db.add(item)

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=JobEventType.ADDITIONAL_WORK_FLAGGED.value,
            note=f"Additional work flagged: {data.description}",
        )
    )

    await db.flush()
    await db.refresh(item)
    return item


async def list_additional_work(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> list[AdditionalWorkItem]:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    result = await db.execute(
        select(AdditionalWorkItem)
        .where(AdditionalWorkItem.job_id == job.id)
        .order_by(AdditionalWorkItem.created_at)
    )
    return list(result.scalars().all())


async def update_additional_work_status(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    new_status: AdditionalWorkStatus,
    *,
    requesting_user: User,
) -> AdditionalWorkItem:
    # Gated to owner/dispatcher at the router level (require_role), so
    # requesting_user is never a technician here — _get_job_for_access's
    # technician-ownership check is a no-op for those roles, reused only
    # for its organization-scoping (cross-org job_id -> 404).
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)
    item = await _get_scoped_additional_work(db, job.id, item_id)
    if item is None:
        raise AdditionalWorkNotFoundError(f"No additional work item {item_id} on this job")

    allowed = _ALLOWED_ADDITIONAL_WORK_TRANSITIONS.get(item.status, set())
    if new_status not in allowed:
        raise InvalidAdditionalWorkStatusTransitionError(
            f"Cannot transition additional work from '{item.status.value}' to '{new_status.value}'"
        )

    item.status = new_status

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=requesting_user.id,
            event_type=_EVENT_TYPE_BY_ADDITIONAL_WORK_STATUS[new_status].value,
            note=f"Additional work {new_status.value}: {item.description}",
        )
    )

    await db.flush()
    await db.refresh(item)
    return item


async def _get_scoped_additional_work(
    db: AsyncSession, job_id: uuid.UUID, item_id: uuid.UUID
) -> AdditionalWorkItem | None:
    result = await db.execute(
        select(AdditionalWorkItem).where(AdditionalWorkItem.id == item_id, AdditionalWorkItem.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def ensure_job_access(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> None:
    """
    Validates the job exists in this org and the requester can act on it,
    raising JobNotFoundError/ForbiddenJobAccessError otherwise — used by
    the document-generation trigger endpoint, which needs exactly this
    check (synchronously, before scheduling the background task) and
    nothing else from the job itself.
    """
    await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)


async def list_documents(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> list[Document]:
    job = await _get_job_for_access(db, organization_id, job_id, requesting_user=requesting_user)

    result = await db.execute(
        select(Document).where(Document.job_id == job.id).order_by(Document.generated_at)
    )
    documents = list(result.scalars().all())
    for document in documents:
        # Transient attribute, not a persisted column — see DocumentRead's
        # own docstring on `download_url`.
        document.download_url = s3_client.generate_presigned_download_url(document.s3_key)
    return documents
