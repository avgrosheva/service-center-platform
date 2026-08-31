"""
Tests for Milestone 15's scheduled warranty-check task
(app.workers.warranty_check_task.run_warranty_check).

Calls the task function directly against the test database — the same
"manually calling the function, not through any invocation machinery"
pattern used for the Milestone 14 PDF renderer — since there's no HTTP
endpoint or real scheduler to drive it through (see the task module's
own docstring for why that wiring is deliberately left out of this
milestone's scope).

Builds jobs directly via SQLAlchemy rather than the HTTP API: the task
scans across every organization's jobs by design (there's no "current
organization" for a system-wide cron job), and exercising every boundary
of its date window needs precise, arbitrary warranty_expires_at values
the API has no way to set directly — completion always computes it as
`today + DEFAULT_WARRANTY_DAYS`.

test_a_failure_during_the_scan_is_logged_and_returns_an_empty_list is
Milestone 17's hardening: before that milestone this task had no
try/except at all (unlike document_tasks.py), so a DB error here would
have propagated unhandled — this proves the fix.
"""

import logging
import uuid
from datetime import date, timedelta

import pytest

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.job import Job, JobStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.workers.warranty_check_task import APPROACHING_EXPIRY_WINDOW_DAYS, run_warranty_check


async def _make_job(session, *, warranty_expires_at: date | None, organization_name: str) -> Job:
    org = Organization(name=organization_name)
    session.add(org)
    await session.flush()

    owner = User(
        organization_id=org.id,
        email=f"{uuid.uuid4().hex}@example.com",
        hashed_password=hash_password("irrelevant-password"),
        full_name="Owner",
        role=UserRole.OWNER,
    )
    session.add(owner)
    await session.flush()

    customer = Customer(organization_id=org.id, full_name="Customer", phone="+79991234567")
    session.add(customer)
    await session.flush()

    job = Job(
        organization_id=org.id,
        customer_id=customer.id,
        created_by_id=owner.id,
        status=JobStatus.COMPLETED if warranty_expires_at is not None else JobStatus.NEW,
        reported_issue="Test issue",
        address_snapshot="Test address",
        warranty_expires_at=warranty_expires_at,
    )
    session.add(job)
    await session.flush()
    return job


@pytest.mark.asyncio
async def test_run_warranty_check_finds_jobs_within_the_window_across_organizations():
    today = date.today()
    async with AsyncSessionLocal() as session:
        expires_today = await _make_job(session, warranty_expires_at=today, organization_name="Org Today")
        expires_soon = await _make_job(
            session, warranty_expires_at=today + timedelta(days=3), organization_name="Org Soon"
        )
        expires_at_window_edge = await _make_job(
            session,
            warranty_expires_at=today + timedelta(days=APPROACHING_EXPIRY_WINDOW_DAYS),
            organization_name="Org Edge",
        )
        expires_past_window = await _make_job(
            session,
            warranty_expires_at=today + timedelta(days=APPROACHING_EXPIRY_WINDOW_DAYS + 1),
            organization_name="Org Too Far",
        )
        already_expired = await _make_job(
            session, warranty_expires_at=today - timedelta(days=1), organization_name="Org Expired"
        )
        never_completed = await _make_job(
            session, warranty_expires_at=None, organization_name="Org Not Completed"
        )
        await session.commit()

    results = await run_warranty_check()
    result_job_ids = {r.job_id for r in results}

    assert expires_today.id in result_job_ids
    assert expires_soon.id in result_job_ids
    assert expires_at_window_edge.id in result_job_ids
    assert expires_past_window.id not in result_job_ids
    assert already_expired.id not in result_job_ids
    assert never_completed.id not in result_job_ids


@pytest.mark.asyncio
async def test_run_warranty_check_reports_correct_days_remaining_and_organization():
    today = date.today()
    async with AsyncSessionLocal() as session:
        job = await _make_job(
            session, warranty_expires_at=today + timedelta(days=4), organization_name="Org Days Remaining"
        )
        await session.commit()

    results = await run_warranty_check()
    matching = [r for r in results if r.job_id == job.id]

    assert len(matching) == 1
    assert matching[0].days_remaining == 4
    assert matching[0].organization_id == job.organization_id
    assert matching[0].warranty_expires_at == job.warranty_expires_at


@pytest.mark.asyncio
async def test_run_warranty_check_runs_without_error_and_returns_a_list():
    # Guards the "runs without error against a realistic dataset" half of
    # the roadmap's testing checklist independent of whatever else has
    # been inserted by the time this runs in the full suite — asserts it
    # completes cleanly and returns a list, not that the list is empty.
    results = await run_warranty_check()
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_a_failure_during_the_scan_is_logged_and_returns_an_empty_list_instead_of_raising(
    monkeypatch, caplog
):
    async def _raise(db):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr("app.workers.warranty_check_task._scan", _raise)

    with caplog.at_level(logging.ERROR, logger="app.workers.warranty_check_task"):
        results = await run_warranty_check()

    assert results == []
    assert "Warranty check failed" in caplog.text
    assert "simulated DB failure" in caplog.text
