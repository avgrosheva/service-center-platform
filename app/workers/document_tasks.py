"""
Document generation background task (Milestone 14) — the first real use
of workers/, invoked via FastAPI BackgroundTasks per the frozen
Background Jobs decision (Technical Blueprint, Section 9).

Deliberately opens its OWN database session via AsyncSessionLocal rather
than reusing the request-scoped session FastAPI's `get_db` dependency
handed the router: by the time a BackgroundTasks callable actually runs,
the request's `get_db` generator may already be torn down, and reusing a
closed/closing session is a well-known FastAPI+SQLAlchemy footgun. This
also happens to be exactly the shape a future arq worker needs (its own
session per task) — per the Technical Blueprint's note that workers/ is
"structured so its functions can be re-registered as arq tasks later
without moving code, only the invocation mechanism changes."

Takes only plain IDs as arguments for the same reason — nothing here
should depend on any object bound to the request's session.

Milestone 17's infrastructure review found this module already satisfies
its hardening bar: `generate_document` wraps the whole render/upload/
persist sequence in try/except+log+rollback, and a failed run simply
leaves no `Document` row behind — the roadmap's own suggested "status
field" for this task, achieved via existence rather than an explicit
status column, since nothing else needed one. No changes were needed
here; `workers/warranty_check_task.py` was the one missing the equivalent
wrapper, fixed in that module instead.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.documents.job_report import JobReportData, MaterialLine, render_job_report_pdf
from app.models.customer import Customer
from app.models.document import Document, DocumentType
from app.models.equipment import Equipment
from app.models.job import Job
from app.models.job_status_history import JobEventType, JobStatusHistory
from app.models.material_item import MaterialItem
from app.models.user import User
from app.storage import s3_client

logger = logging.getLogger(__name__)


async def generate_document(
    job_id: uuid.UUID, organization_id: uuid.UUID, document_type: DocumentType, actor_id: uuid.UUID
) -> None:
    """
    Renders a PDF from the job's current data, uploads it to S3, and
    persists a Document row + a `document_generated` timeline entry — all
    in one commit, or none of it, on failure.

    The job's existence/org-scoping was already validated synchronously
    in the router before this was scheduled (job_items_service.ensure_job_access),
    so a missing job here would mean it was deleted between the request
    and this task running — logged, not raised, since there's no request
    left to surface an error to.
    """
    async with AsyncSessionLocal() as db:
        try:
            await _generate(db, job_id, organization_id, document_type, actor_id)
            await db.commit()
        except Exception:
            logger.exception("Document generation failed for job %s", job_id)
            await db.rollback()


async def _generate(
    db: AsyncSession, job_id: uuid.UUID, organization_id: uuid.UUID, document_type: DocumentType, actor_id: uuid.UUID
) -> None:
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == organization_id))
    ).scalar_one_or_none()
    if job is None:
        logger.error("Document generation skipped: job %s not found in org %s", job_id, organization_id)
        return

    data = await _build_job_report_data(db, job, document_type)
    pdf_bytes = render_job_report_pdf(data)

    key = f"{organization_id}/jobs/{job_id}/documents/{uuid.uuid4()}.pdf"
    s3_client.upload_bytes(key, pdf_bytes, content_type="application/pdf")

    db.add(Document(job_id=job.id, type=document_type, s3_key=key))
    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=actor_id,
            event_type=JobEventType.DOCUMENT_GENERATED.value,
            note=f"{document_type.value} generated",
        )
    )


async def _build_job_report_data(db: AsyncSession, job: Job, document_type: DocumentType) -> JobReportData:
    customer = (await db.execute(select(Customer).where(Customer.id == job.customer_id))).scalar_one()

    equipment_description = None
    if job.equipment_id is not None:
        equipment = (
            await db.execute(select(Equipment).where(Equipment.id == job.equipment_id))
        ).scalar_one_or_none()
        if equipment is not None:
            parts = [p for p in (equipment.brand, equipment.model) if p]
            label = " ".join(parts) if parts else equipment.type
            equipment_description = f"{equipment.type} ({label})" if parts else equipment.type

    technician_name = None
    if job.assigned_technician_id is not None:
        technician = (
            await db.execute(select(User).where(User.id == job.assigned_technician_id))
        ).scalar_one_or_none()
        if technician is not None:
            technician_name = technician.full_name

    materials_result = await db.execute(
        select(MaterialItem).where(MaterialItem.job_id == job.id).order_by(MaterialItem.created_at)
    )
    materials = [
        MaterialLine(name=m.name, quantity=m.quantity, unit_cost=m.unit_cost)
        for m in materials_result.scalars().all()
    ]

    # "Work done (from timeline/notes)" per the roadmap — every timeline
    # entry that carries a human-written note, in chronological order.
    notes_result = await db.execute(
        select(JobStatusHistory.note)
        .where(JobStatusHistory.job_id == job.id, JobStatusHistory.note.is_not(None))
        .order_by(JobStatusHistory.created_at)
    )
    work_notes = [note for (note,) in notes_result.all()]

    return JobReportData(
        job_id=str(job.id),
        document_type=document_type.value,
        customer_name=customer.full_name,
        address=job.address_snapshot,
        status=job.status.value,
        reported_issue=job.reported_issue,
        generated_at=datetime.now(timezone.utc),
        equipment_description=equipment_description,
        technician_name=technician_name,
        materials=materials,
        work_notes=work_notes,
        is_warranty_claim=job.is_warranty_claim,
        warranty_expires_at=job.warranty_expires_at,
    )
