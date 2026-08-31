"""
Tests for Milestone 16's dashboard endpoints: GET /dashboard/summary and
GET /dashboard/metrics.

The roadmap's own risk assessment for this milestone is explicit: the
danger is metrics that are *silently* wrong (off-by-one date ranges,
double-counting), not the query failing to run. So every metric here is
checked against a value hand-computed from a deterministic seed dataset —
never just "the endpoint returned 200."

The seed dataset is built directly via SQLAlchemy (AsyncSessionLocal),
not by driving jobs through their full HTTP lifecycle: dashboard
correctness depends on exact created_at/completed_at/paid_at timestamps,
which the API has no way to backdate, and a real multi-day job lifecycle
can't be produced by wall-clock-bound test execution anyway. This is the
same pattern used in test_jobs.py's warranty tests and
test_warranty_check_task.py.

Hand-computed scenario (all in one organization unless noted):

  Customers: C1 (2 jobs), C2 (1 job), C3 (1 job, cancelled), C4 (1 job)
    -> 4 customers with jobs, 1 of them (C1) has more than one
    -> repeat_customer_rate = 1/4 = 0.25

  Job1 (C1): completed, Tech A, created 10d ago, completed 5d ago
             (completion time = 5 days = 120 hours), is_warranty_claim=True
             payment: 1000.00 paid 5d ago
  Job2 (C1): status=new, scheduled_at 1d ago -> active + delayed
  Job3 (C2): completed, Tech B, created 8d ago, completed 2d ago
             (completion time = 6 days = 144 hours)
             payment: 2000.00 paid 2d ago
  Job4 (C3): status=cancelled -> neither active, delayed, nor completed
  Job5 (C4): status=in_progress, scheduled_at 2d ago -> active + delayed

  Additional work: 2 items on Job1 (pending, approved) = unbilled;
                    2 items on Job3 (billed, rejected) = not unbilled

  Expected /dashboard/summary:
    active_jobs = 2              (Job2, Job5)
    delayed_jobs = 2             (Job2, Job5)
    completed_jobs = 2           (Job1, Job3)
    unbilled_additional_work = 2 (the pending + approved items)

  Expected /dashboard/metrics:
    avg_completion_time_hours = (120 + 144) / 2 = 132.0
    revenue_per_technician = [Tech A: 1000.00, Tech B: 2000.00]
    average_order_value = (1000.00 + 2000.00) / 2 = 1500.00
    repeat_customer_rate = 0.25
    warranty_case_count = 1      (Job1)
"""

import time as time_module
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import AsyncSessionLocal
from app.main import app
from app.models.additional_work_item import AdditionalWorkItem, AdditionalWorkStatus
from app.models.customer import Customer
from app.models.job import Job, JobStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register_org(client: AsyncClient, *, password: str = "owner-password-1") -> dict:
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Org Owner",
        "email": _unique_email(),
        "password": password,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    access_token = response.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(access_token))
    profile = me.json()

    return {"access_token": access_token, "organization_id": profile["organization_id"], "user_id": profile["id"]}


async def _create_member(client: AsyncClient, owner_token: str, *, role: str, full_name: str) -> dict:
    email = _unique_email()
    password = "member-password-1"
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": full_name, "role": role, "password": password},
        headers=_auth_headers(owner_token),
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    return {"id": user_id, "full_name": full_name, "access_token": login.json()["access_token"]}


async def _get_dashboard(client, token, *, date_from: str | None = None, date_to: str | None = None):
    params = {}
    if date_from is not None:
        params["date_from"] = date_from
    if date_to is not None:
        params["date_to"] = date_to
    summary = await client.get("/api/v1/dashboard/summary", params=params, headers=_auth_headers(token))
    metrics = await client.get("/api/v1/dashboard/metrics", params=params, headers=_auth_headers(token))
    assert summary.status_code == 200, summary.text
    assert metrics.status_code == 200, metrics.text
    return summary.json(), metrics.json()


async def _seed_dashboard_dataset(organization_id: str, owner_id: str, tech_a_id: str, tech_b_id: str) -> None:
    now = datetime.now(timezone.utc)
    org_id = uuid.UUID(organization_id)
    owner_uuid = uuid.UUID(owner_id)
    tech_a_uuid = uuid.UUID(tech_a_id)
    tech_b_uuid = uuid.UUID(tech_b_id)

    async with AsyncSessionLocal() as session:
        c1 = Customer(organization_id=org_id, full_name="C1", phone="+79990000001")
        c2 = Customer(organization_id=org_id, full_name="C2", phone="+79990000002")
        c3 = Customer(organization_id=org_id, full_name="C3", phone="+79990000003")
        c4 = Customer(organization_id=org_id, full_name="C4", phone="+79990000004")
        session.add_all([c1, c2, c3, c4])
        await session.flush()

        job1 = Job(
            organization_id=org_id,
            customer_id=c1.id,
            assigned_technician_id=tech_a_uuid,
            created_by_id=owner_uuid,
            status=JobStatus.COMPLETED,
            reported_issue="Job1",
            address_snapshot="Addr1",
            created_at=now - timedelta(days=10),
            completed_at=now - timedelta(days=5),
            is_warranty_claim=True,
        )
        job2 = Job(
            organization_id=org_id,
            customer_id=c1.id,
            created_by_id=owner_uuid,
            status=JobStatus.NEW,
            reported_issue="Job2",
            address_snapshot="Addr2",
            scheduled_at=now - timedelta(days=1),
        )
        job3 = Job(
            organization_id=org_id,
            customer_id=c2.id,
            assigned_technician_id=tech_b_uuid,
            created_by_id=owner_uuid,
            status=JobStatus.COMPLETED,
            reported_issue="Job3",
            address_snapshot="Addr3",
            created_at=now - timedelta(days=8),
            completed_at=now - timedelta(days=2),
        )
        job4 = Job(
            organization_id=org_id,
            customer_id=c3.id,
            created_by_id=owner_uuid,
            status=JobStatus.CANCELLED,
            reported_issue="Job4",
            address_snapshot="Addr4",
        )
        job5 = Job(
            organization_id=org_id,
            customer_id=c4.id,
            assigned_technician_id=tech_a_uuid,
            created_by_id=owner_uuid,
            status=JobStatus.IN_PROGRESS,
            reported_issue="Job5",
            address_snapshot="Addr5",
            scheduled_at=now - timedelta(days=2),
        )
        session.add_all([job1, job2, job3, job4, job5])
        await session.flush()

        session.add_all(
            [
                Payment(
                    job_id=job1.id,
                    amount="1000.00",
                    method=PaymentMethod.CASH,
                    status=PaymentStatus.PAID,
                    paid_at=now - timedelta(days=5),
                ),
                Payment(
                    job_id=job3.id,
                    amount="2000.00",
                    method=PaymentMethod.CARD,
                    status=PaymentStatus.PAID,
                    paid_at=now - timedelta(days=2),
                ),
                AdditionalWorkItem(
                    organization_id=org_id,
                    job_id=job1.id,
                    description="AW pending",
                    price="10.00",
                    status=AdditionalWorkStatus.PENDING,
                    created_by_id=owner_uuid,
                ),
                AdditionalWorkItem(
                    organization_id=org_id,
                    job_id=job1.id,
                    description="AW approved",
                    price="20.00",
                    status=AdditionalWorkStatus.APPROVED,
                    created_by_id=owner_uuid,
                ),
                AdditionalWorkItem(
                    organization_id=org_id,
                    job_id=job3.id,
                    description="AW billed",
                    price="30.00",
                    status=AdditionalWorkStatus.BILLED,
                    created_by_id=owner_uuid,
                ),
                AdditionalWorkItem(
                    organization_id=org_id,
                    job_id=job3.id,
                    description="AW rejected",
                    price="40.00",
                    status=AdditionalWorkStatus.REJECTED,
                    created_by_id=owner_uuid,
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_summary_matches_hand_computed_values(client):
    owner = await _register_org(client)
    tech_a = await _create_member(client, owner["access_token"], role="technician", full_name="Tech A")
    tech_b = await _create_member(client, owner["access_token"], role="technician", full_name="Tech B")
    await _seed_dashboard_dataset(owner["organization_id"], owner["user_id"], tech_a["id"], tech_b["id"])

    summary, _ = await _get_dashboard(client, owner["access_token"])

    assert summary["active_jobs"] == 2
    assert summary["delayed_jobs"] == 2
    assert summary["completed_jobs"] == 2
    assert summary["unbilled_additional_work"] == 2


@pytest.mark.asyncio
async def test_metrics_match_hand_computed_values(client):
    owner = await _register_org(client)
    tech_a = await _create_member(client, owner["access_token"], role="technician", full_name="Tech A")
    tech_b = await _create_member(client, owner["access_token"], role="technician", full_name="Tech B")
    await _seed_dashboard_dataset(owner["organization_id"], owner["user_id"], tech_a["id"], tech_b["id"])

    _, metrics = await _get_dashboard(client, owner["access_token"])

    assert metrics["avg_completion_time_hours"] == pytest.approx(132.0, abs=0.01)

    revenue = {r["technician_id"]: float(r["revenue"]) for r in metrics["revenue_per_technician"]}
    assert revenue == {tech_a["id"]: 1000.00, tech_b["id"]: 2000.00}

    assert float(metrics["average_order_value"]) == pytest.approx(1500.00, abs=0.01)
    assert metrics["repeat_customer_rate"] == pytest.approx(0.25, abs=1e-9)
    assert metrics["warranty_case_count"] == 1


@pytest.mark.asyncio
async def test_summary_and_metrics_are_all_zero_with_no_data(client):
    owner = await _register_org(client)

    summary, metrics = await _get_dashboard(client, owner["access_token"])

    assert summary == {
        "active_jobs": 0,
        "delayed_jobs": 0,
        "completed_jobs": 0,
        "unbilled_additional_work": 0,
    }
    assert metrics["avg_completion_time_hours"] is None
    assert metrics["revenue_per_technician"] == []
    assert metrics["average_order_value"] is None
    assert metrics["repeat_customer_rate"] == 0.0
    assert metrics["warranty_case_count"] == 0


@pytest.mark.asyncio
async def test_date_range_filtering_is_inclusive_on_both_boundaries(client):
    owner = await _register_org(client)
    org_id = uuid.UUID(owner["organization_id"])
    owner_id = uuid.UUID(owner["user_id"])
    today = datetime.now(timezone.utc).date()
    day1, day2, day3 = today - timedelta(days=2), today - timedelta(days=1), today

    async with AsyncSessionLocal() as session:
        customer = Customer(organization_id=org_id, full_name="Boundary Customer", phone="+79990000009")
        session.add(customer)
        await session.flush()

        def _completed_job(label: str, day) -> Job:
            return Job(
                organization_id=org_id,
                customer_id=customer.id,
                created_by_id=owner_id,
                status=JobStatus.COMPLETED,
                reported_issue=label,
                address_snapshot="Addr",
                created_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                completed_at=datetime.combine(day, datetime.min.time().replace(hour=12), tzinfo=timezone.utc),
            )

        session.add_all(
            [_completed_job("Day1 job", day1), _completed_job("Day2 job", day2), _completed_job("Day3 job", day3)]
        )
        await session.commit()

    # [day1, day2] should include exactly the day1 and day2 jobs, not day3.
    summary, _ = await _get_dashboard(
        client, owner["access_token"], date_from=day1.isoformat(), date_to=day2.isoformat()
    )
    assert summary["completed_jobs"] == 2

    # [day2, day2] (a single-day range) should include only the day2 job —
    # proving date_to isn't silently truncating to 00:00 that day (which
    # would exclude the noon completion and wrongly return 0).
    summary_single_day, _ = await _get_dashboard(
        client, owner["access_token"], date_from=day2.isoformat(), date_to=day2.isoformat()
    )
    assert summary_single_day["completed_jobs"] == 1

    # No range at all: all three.
    summary_all, _ = await _get_dashboard(client, owner["access_token"])
    assert summary_all["completed_jobs"] == 3


@pytest.mark.asyncio
async def test_technician_is_blocked_from_both_dashboard_endpoints(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician", full_name="Tech")
    headers = _auth_headers(technician["access_token"])

    assert (await client.get("/api/v1/dashboard/summary", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/dashboard/metrics", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_dispatcher_can_view_dashboard(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher", full_name="Dispatcher")

    summary, metrics = await _get_dashboard(client, dispatcher["access_token"])

    assert summary["active_jobs"] == 0
    assert metrics["warranty_case_count"] == 0


@pytest.mark.asyncio
async def test_cross_org_data_never_leaks_into_another_organizations_dashboard(client):
    org_a_owner = await _register_org(client)
    tech_a = await _create_member(client, org_a_owner["access_token"], role="technician", full_name="Tech A")
    tech_b = await _create_member(client, org_a_owner["access_token"], role="technician", full_name="Tech B")
    await _seed_dashboard_dataset(
        org_a_owner["organization_id"], org_a_owner["user_id"], tech_a["id"], tech_b["id"]
    )

    org_b_owner = await _register_org(client)

    summary_b, metrics_b = await _get_dashboard(client, org_b_owner["access_token"])

    assert summary_b == {
        "active_jobs": 0,
        "delayed_jobs": 0,
        "completed_jobs": 0,
        "unbilled_additional_work": 0,
    }
    assert metrics_b["revenue_per_technician"] == []
    assert metrics_b["warranty_case_count"] == 0

    # Org A's own numbers are unaffected by Org B existing.
    summary_a, _ = await _get_dashboard(client, org_a_owner["access_token"])
    assert summary_a["completed_jobs"] == 2


@pytest.mark.asyncio
async def test_dashboard_queries_complete_quickly_against_a_few_hundred_jobs(client):
    owner = await _register_org(client)
    org_id = uuid.UUID(owner["organization_id"])
    owner_id = uuid.UUID(owner["user_id"])
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        customers = [
            Customer(organization_id=org_id, full_name=f"Perf Customer {i}", phone=f"+7999000{i:04d}")
            for i in range(50)
        ]
        session.add_all(customers)
        await session.flush()

        jobs = []
        statuses = [
            JobStatus.NEW,
            JobStatus.ASSIGNED,
            JobStatus.IN_PROGRESS,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
        ]
        for i in range(300):
            customer = customers[i % len(customers)]
            status = statuses[i % len(statuses)]
            jobs.append(
                Job(
                    organization_id=org_id,
                    customer_id=customer.id,
                    created_by_id=owner_id,
                    status=status,
                    reported_issue=f"Perf job {i}",
                    address_snapshot="Addr",
                    scheduled_at=now - timedelta(days=i % 10),
                    completed_at=(now - timedelta(days=i % 10)) if status == JobStatus.COMPLETED else None,
                    is_warranty_claim=(i % 7 == 0),
                )
            )
        session.add_all(jobs)
        await session.commit()

    started = time_module.monotonic()
    summary, metrics = await _get_dashboard(client, owner["access_token"])
    elapsed = time_module.monotonic() - started

    assert summary["completed_jobs"] == len([j for j in jobs if j.status == JobStatus.COMPLETED])
    assert elapsed < 5.0, f"dashboard queries took {elapsed:.2f}s against 300 jobs — investigate before shipping"
