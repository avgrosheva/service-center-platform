"""
Seed / demo data script (Milestone 19).

Run with: python -m app.seed_demo_data

Creates one demonstration organization and walks it through every
primary workflow named in the Product Definition's Section 7 — using the
real service-layer functions (job_service, job_items_service,
payment_service, equipment_service, the document-generation worker), not
raw INSERTs — so this script doubles as an end-to-end smoke test that
those workflows still compose correctly together, exactly what this
milestone's own checklist asks for ("Full manual smoke test of every
primary workflow... end to end, using the seed data").

Dataset, and which Section 7 workflow each piece demonstrates:

- Org "Demo Repairs Co.", one owner, one dispatcher, two technicians,
  three customers, one piece of equipment each for the first two.
- Job 1 (completed): full lifecycle new -> assigned -> en_route ->
  in_progress -> awaiting_approval -> completed (7.1 intake, 7.2
  assignment, 7.3 on-site execution via a logged material + status
  notes), an additional-work item approved then billed (7.4), a paid
  payment (7.6), and a generated job-report PDF (7.5 — via
  workers.document_tasks directly, proving that pipeline still works
  against real seeded data, not just pytest's mocks).
- Job 2 (same equipment as Job 1, created after Job 1 completes): proves
  7.7 warranty handling live — auto-flags as a warranty claim via the
  real auto-detection logic in job_service, not a forced override.
  Completed with an unpaid payment (feeds the dashboard's "unpaid jobs"
  signal).
- Job 3 (in_progress, assigned): a still-pending additional-work item,
  demonstrating the "needs a decision" half of 7.4 that Job 1's
  already-resolved item doesn't cover.
- Job 4 (new, unassigned): a bare intake-only record (7.1 with nothing
  else yet).
- Job 5 (cancelled): the cancellation path.

Ends by calling dashboard_service.get_summary/get_metrics on the seeded
org and printing the result — a live check that the whole pipeline
(jobs -> materials -> additional work -> payments -> warranty) produces
sane aggregate numbers, not just that each piece works in isolation.

Not idempotent by design: every run creates a brand-new organization
(name suffixed with a fresh UUID fragment) rather than upserting into an
existing one. Running it twice just gives two demo orgs, which is
harmless — a throwaway demo dataset doesn't need conflict-detection
logic a real multi-tenant write path would.
"""

import asyncio
import uuid

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.additional_work_item import AdditionalWorkStatus
from app.models.customer import Customer
from app.models.document import DocumentType
from app.models.job import JobStatus
from app.models.organization import Organization
from app.models.payment import PaymentMethod, PaymentStatus
from app.models.user import User, UserRole
from app.schemas.additional_work_item import AdditionalWorkItemCreate
from app.schemas.equipment import EquipmentCreate
from app.schemas.job import JobCreate
from app.schemas.material_item import MaterialItemCreate
from app.schemas.payment import PaymentUpsert
from app.services import dashboard_service, equipment_service, job_items_service, job_service, payment_service
from app.workers import document_tasks


async def _seed() -> None:
    async with AsyncSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        org = Organization(name=f"Demo Repairs Co. {suffix}")
        db.add(org)
        await db.flush()

        owner = User(
            organization_id=org.id,
            email=f"owner-{suffix}@demo.local",
            hashed_password=hash_password("demo-password-123"),
            full_name="Olga Owner",
            role=UserRole.OWNER,
        )
        dispatcher = User(
            organization_id=org.id,
            email=f"dispatcher-{suffix}@demo.local",
            hashed_password=hash_password("demo-password-123"),
            full_name="Dmitry Dispatcher",
            role=UserRole.DISPATCHER,
        )
        tech_a = User(
            organization_id=org.id,
            email=f"tech-a-{suffix}@demo.local",
            hashed_password=hash_password("demo-password-123"),
            full_name="Sergey Volkov",
            role=UserRole.TECHNICIAN,
        )
        tech_b = User(
            organization_id=org.id,
            email=f"tech-b-{suffix}@demo.local",
            hashed_password=hash_password("demo-password-123"),
            full_name="Ivan Titov",
            role=UserRole.TECHNICIAN,
        )
        db.add_all([owner, dispatcher, tech_a, tech_b])
        await db.flush()

        customer_1 = Customer(organization_id=org.id, full_name="Anna Ivanova", phone="+79161234567")
        customer_2 = Customer(organization_id=org.id, full_name="Boris Sidorov", phone="+79261234567")
        customer_3 = Customer(organization_id=org.id, full_name="Elena Kuznetsova", phone="+79031234567")
        db.add_all([customer_1, customer_2, customer_3])
        await db.flush()

        equipment_1 = await equipment_service.create_equipment(
            db,
            org.id,
            customer_1.id,
            EquipmentCreate(
                type="AC unit", brand="Daikin", model="FTXS35", installation_address="5 Pushkina St, Apt 12"
            ),
        )
        equipment_2 = await equipment_service.create_equipment(
            db,
            org.id,
            customer_2.id,
            EquipmentCreate(type="Refrigerator", brand="LG", installation_address="18 Lenina Ave"),
        )
        await equipment_service.create_equipment(
            db, org.id, customer_3.id, EquipmentCreate(type="Boiler", installation_address="3 Sovetskaya St")
        )
        await db.commit()

        # --- Job 1: full completed lifecycle, additional work billed, paid, documented ---
        job1 = await job_service.create_job(
            db,
            org.id,
            owner.id,
            JobCreate(
                customer_id=customer_1.id,
                equipment_id=equipment_1.id,
                reported_issue="AC unit blowing warm air, compressor making noise",
            ),
        )
        await db.commit()

        await job_service.assign_technician(db, org.id, job1.id, tech_a.id, actor=owner)
        await db.commit()

        await job_service.change_status(
            db, org.id, job1.id, JobStatus.EN_ROUTE, note="On the way to the customer", actor=tech_a
        )
        await db.commit()

        await job_items_service.add_material(
            db,
            org.id,
            job1.id,
            MaterialItemCreate(name="Refrigerant R410A", quantity="2.5", unit_cost="1500.00"),
            requesting_user=tech_a,
        )
        await db.commit()

        await job_service.change_status(
            db, org.id, job1.id, JobStatus.IN_PROGRESS, note="Diagnosed: worn compressor relay", actor=tech_a
        )
        await db.commit()

        additional_work = await job_items_service.flag_additional_work(
            db,
            org.id,
            job1.id,
            AdditionalWorkItemCreate(description="Replace worn compressor relay", price="45.00"),
            requesting_user=tech_a,
        )
        await db.commit()
        await job_items_service.update_additional_work_status(
            db, org.id, job1.id, additional_work.id, AdditionalWorkStatus.APPROVED, requesting_user=owner
        )
        await db.commit()
        await job_items_service.update_additional_work_status(
            db, org.id, job1.id, additional_work.id, AdditionalWorkStatus.BILLED, requesting_user=owner
        )
        await db.commit()

        await job_service.change_status(
            db,
            org.id,
            job1.id,
            JobStatus.AWAITING_APPROVAL,
            note="Repair complete, awaiting customer sign-off",
            actor=tech_a,
        )
        await db.commit()
        await job_service.change_status(db, org.id, job1.id, JobStatus.COMPLETED, note=None, actor=owner)
        await db.commit()

        await payment_service.upsert_payment(
            db,
            org.id,
            job1.id,
            PaymentUpsert(amount="4500.00", method=PaymentMethod.CARD, status=PaymentStatus.PAID),
        )
        await db.commit()

        await document_tasks.generate_document(job1.id, org.id, DocumentType.JOB_REPORT, owner.id)

        # --- Job 2: same equipment, created after Job 1 completes -> auto-flags as warranty claim ---
        job2 = await job_service.create_job(
            db,
            org.id,
            dispatcher.id,
            JobCreate(
                customer_id=customer_1.id,
                equipment_id=equipment_1.id,
                reported_issue="Same AC unit stopped cooling again",
            ),
        )
        await db.commit()

        await job_service.assign_technician(db, org.id, job2.id, tech_a.id, actor=dispatcher)
        await db.commit()
        for target_status in (JobStatus.EN_ROUTE, JobStatus.IN_PROGRESS, JobStatus.AWAITING_APPROVAL, JobStatus.COMPLETED):
            await job_service.change_status(db, org.id, job2.id, target_status, note=None, actor=tech_a)
            await db.commit()

        await payment_service.upsert_payment(
            db,
            org.id,
            job2.id,
            PaymentUpsert(amount="3200.00", method=PaymentMethod.CASH, status=PaymentStatus.UNPAID),
        )
        await db.commit()

        # --- Job 3: mid-flight, with a still-pending additional-work decision ---
        job3 = await job_service.create_job(
            db,
            org.id,
            dispatcher.id,
            JobCreate(
                customer_id=customer_2.id, equipment_id=equipment_2.id, reported_issue="Refrigerator not cooling properly"
            ),
        )
        await db.commit()
        await job_service.assign_technician(db, org.id, job3.id, tech_b.id, actor=dispatcher)
        await db.commit()
        await job_service.change_status(
            db, org.id, job3.id, JobStatus.EN_ROUTE, note="Heading to the site", actor=tech_b
        )
        await db.commit()
        await job_service.change_status(
            db, org.id, job3.id, JobStatus.IN_PROGRESS, note="Compressor is failing, may need replacement", actor=tech_b
        )
        await db.commit()
        await job_items_service.flag_additional_work(
            db,
            org.id,
            job3.id,
            AdditionalWorkItemCreate(description="Replace failing compressor", price="220.00"),
            requesting_user=tech_b,
        )
        await db.commit()

        # --- Job 4: bare intake only ---
        await job_service.create_job(
            db,
            org.id,
            dispatcher.id,
            JobCreate(
                customer_id=customer_1.id,
                reported_issue="New AC install consultation requested",
                address="5 Pushkina St, Apt 12",
            ),
        )
        await db.commit()

        # --- Job 5: cancelled ---
        job5 = await job_service.create_job(
            db,
            org.id,
            owner.id,
            JobCreate(customer_id=customer_2.id, reported_issue="Customer called about a squeaky fridge", address="18 Lenina Ave"),
        )
        await db.commit()
        await job_service.cancel_job(db, org.id, job5.id, actor=owner)
        await db.commit()

        summary = await dashboard_service.get_summary(db, org.id, date_from=None, date_to=None)
        metrics = await dashboard_service.get_metrics(db, org.id, date_from=None, date_to=None)

        print(f"Seeded organization: {org.name} ({org.id})")
        print(f"  Owner login:      owner-{suffix}@demo.local / demo-password-123")
        print(f"  Dispatcher login: dispatcher-{suffix}@demo.local / demo-password-123")
        print(f"  Technician login: tech-a-{suffix}@demo.local / demo-password-123")
        print(f"Dashboard summary: {summary}")
        print(f"Dashboard metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(_seed())
