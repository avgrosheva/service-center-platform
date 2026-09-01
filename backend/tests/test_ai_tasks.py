"""
Tests for Milestone 18's /ai/* endpoints and the ai_tasks background
processing lifecycle, run against an app instance built with AI_ENABLED=
true (see test_ai_route_registration.py for the registration-gating
tests themselves).

Every test here monkeypatches app.workers.ai_tasks._call_claude — the one
function that actually talks to the Anthropic API — so the suite never
makes a real network call or spends real API cost, while still exercising
the complete pending -> processing -> done/failed lifecycle end to end.
This mirrors Milestone 17's tests monkeypatching s3_client.upload_bytes to
simulate a background-task failure without touching real infrastructure.

Two structural notes carried over from Milestone 14's test_documents.py:

- With httpx's ASGITransport (no real network socket), Starlette runs a
  request's BackgroundTasks *before* control returns to the client. So by
  the time `await client.post(...)` returns, the task has already been
  fully processed — but the JSON body of THAT response was serialized
  from the route handler's return value *before* the background task
  ran, so it still correctly reflects `status="pending"`. A GET made
  right after shows the now-current `"done"`/`"failed"` state. That
  pending-in-the-response / done-a-moment-later split is real evidence
  the request/response cycle isn't blocked on the Claude call — not an
  artifact of the test harness.
- test_task_is_marked_processing_while_the_claude_call_is_in_flight below
  calls `app.workers.ai_tasks.process_ai_task` directly (bypassing HTTP
  entirely) specifically so the monkeypatched `_call_claude` can pause
  mid-flight and observe the task's `status` from a separate DB session —
  proving the `processing` intermediate state is a real, durably
  committed row, not just a status enum value that never gets written.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.main import create_app
from app.models.additional_work_item import AdditionalWorkItem
from app.models.job import Job
from app.models.payment import Payment
from app.workers import ai_tasks


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    settings = get_settings().model_copy(update={"ai_enabled": True})
    app = create_app(settings)
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


async def _create_member(client: AsyncClient, owner_token: str, *, role: str) -> dict:
    email = _unique_email()
    password = "member-password-1"
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": f"Test {role.title()}", "role": role, "password": password},
        headers=_auth_headers(owner_token),
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    return {"id": user_id, "access_token": login.json()["access_token"]}


async def _create_customer(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/api/v1/customers",
        json={"full_name": "Ivan Petrov", "phone": "+7 999 123-45-67"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_job(client: AsyncClient, token: str, *, customer_id: str) -> dict:
    response = await client.post(
        "/api/v1/jobs",
        json={"customer_id": customer_id, "reported_issue": "AC not cooling", "address": "Somewhere"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _assign(client: AsyncClient, token: str, job_id: str, technician_id: str) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/assign",
        json={"technician_id": technician_id},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _mock_claude_success(output: str = "mocked AI output"):
    async def _fake(prompt: str) -> str:
        return output

    return _fake


def _mock_claude_failure(message: str = "simulated Anthropic failure"):
    async def _fake(prompt: str) -> str:
        raise RuntimeError(message)

    return _fake


@pytest.mark.asyncio
async def test_voice_note_creates_pending_task_and_transitions_to_done(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_success("Cleaned note text"))
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    create_response = await client.post(
        "/api/v1/ai/voice-note", json={"transcript": "uh so I replaced the, uh, compressor relay"}, headers=headers
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["status"] == "pending"
    assert created["task_type"] == "voice_transcription"
    assert created["job_id"] is None

    poll_response = await client.get(f"/api/v1/ai/tasks/{created['id']}", headers=headers)
    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["status"] == "done"
    assert polled["output"] == "Cleaned note text"
    assert polled["error"] is None
    assert polled["completed_at"] is not None


@pytest.mark.asyncio
async def test_job_summary_task_transitions_to_done(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_success("Friendly summary for the customer"))
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    create_response = await client.post(f"/api/v1/ai/jobs/{job['id']}/summary", headers=headers)
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["status"] == "pending"
    assert created["job_id"] == job["id"]
    assert created["task_type"] == "summary"

    polled = (await client.get(f"/api/v1/ai/tasks/{created['id']}", headers=headers)).json()
    assert polled["status"] == "done"
    assert polled["output"] == "Friendly summary for the customer"


@pytest.mark.asyncio
async def test_query_task_transitions_to_done(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_success("There are 3 active jobs."))
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    create_response = await client.post(
        "/api/v1/ai/query", json={"query": "How many active jobs do we have?"}, headers=headers
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["status"] == "pending"
    assert created["task_type"] == "qa_query"
    assert created["job_id"] is None

    polled = (await client.get(f"/api/v1/ai/tasks/{created['id']}", headers=headers)).json()
    assert polled["status"] == "done"
    assert polled["output"] == "There are 3 active jobs."


@pytest.mark.asyncio
async def test_a_failed_claude_call_marks_the_task_failed_with_the_error_captured(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_failure("simulated Anthropic failure"))
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    create_response = await client.post(
        "/api/v1/ai/voice-note", json={"transcript": "something"}, headers=headers
    )
    assert create_response.status_code == 201, create_response.text

    polled = (await client.get(f"/api/v1/ai/tasks/{create_response.json()['id']}", headers=headers)).json()
    assert polled["status"] == "failed"
    assert polled["output"] is None
    assert "simulated Anthropic failure" in polled["error"]
    assert polled["completed_at"] is not None


@pytest.mark.asyncio
async def test_ai_never_writes_to_job_additional_work_or_payment_state(client, monkeypatch):
    # The hard rule: an AI suggestion is text in ai_tasks.output for a
    # human to act on manually — it must never itself create an
    # AdditionalWorkItem, change the Job's status, or touch a Payment.
    monkeypatch.setattr(
        ai_tasks, "_call_claude", _mock_claude_success("Suggest: replace the worn compressor relay ($45).")
    )
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    job_id = uuid.UUID(job["id"])

    create_response = await client.post(
        f"/api/v1/ai/jobs/{job['id']}/suggest-additional-work", headers=headers
    )
    assert create_response.status_code == 201, create_response.text

    polled = (await client.get(f"/api/v1/ai/tasks/{create_response.json()['id']}", headers=headers)).json()
    assert polled["status"] == "done"
    assert "compressor relay" in polled["output"]

    # The suggestion landed only in the ai_task row above — nothing else
    # in the database changed as a side effect of it.
    async with AsyncSessionLocal() as db:
        additional_work_items = (
            await db.execute(select(AdditionalWorkItem).where(AdditionalWorkItem.job_id == job_id))
        ).scalars().all()
        assert additional_work_items == []

        db_job = await db.get(Job, job_id)
        assert db_job.status.value == "new"  # unchanged from creation

        payments = (await db.execute(select(Payment).where(Payment.job_id == job_id))).scalars().all()
        assert payments == []


@pytest.mark.asyncio
async def test_task_is_marked_processing_while_the_claude_call_is_in_flight(client, monkeypatch):
    observed_status = {}

    async def _observe_and_return(prompt: str) -> str:
        async with AsyncSessionLocal() as db:
            task = await db.get(ai_tasks.AITask, task_id)
            observed_status["value"] = task.status.value
        return "done output"

    monkeypatch.setattr(ai_tasks, "_call_claude", _observe_and_return)

    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    # Create the task via the DB-only service call directly (not through
    # HTTP) so this test controls exactly when process_ai_task runs,
    # rather than relying on ASGITransport's synchronous BackgroundTasks
    # timing — see the module docstring for why.
    from app.services import ai_service

    async with AsyncSessionLocal() as db:
        task = await ai_service.create_voice_note_task(db, uuid.UUID(owner["organization_id"]), "raw transcript")
        await db.commit()
        task_id = task.id

    await ai_tasks.process_ai_task(task_id)

    assert observed_status["value"] == "processing"

    poll_response = await client.get(f"/api/v1/ai/tasks/{task_id}", headers=headers)
    assert poll_response.json()["status"] == "done"
    assert poll_response.json()["output"] == "done output"


@pytest.mark.asyncio
async def test_technician_can_use_ai_on_their_own_assigned_job(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_success("summary"))
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician["id"])

    response = await client.post(
        f"/api/v1/ai/jobs/{job['id']}/summary", headers=_auth_headers(technician["access_token"])
    )

    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_technician_gets_403_on_a_job_not_assigned_to_them(client):
    owner = await _register_org(client)
    technician_a = await _create_member(client, owner["access_token"], role="technician")
    technician_b = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician_b["id"])

    response = await client.post(
        f"/api/v1/ai/jobs/{job['id']}/summary", headers=_auth_headers(technician_a["access_token"])
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(client, org_a_owner["access_token"], customer_id=org_a_customer["id"])

    org_b_owner = await _register_org(client)

    response = await client.post(
        f"/api/v1/ai/jobs/{org_a_job['id']}/summary", headers=_auth_headers(org_b_owner["access_token"])
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_task_cross_org_is_404(client, monkeypatch):
    monkeypatch.setattr(ai_tasks, "_call_claude", _mock_claude_success("x"))
    org_a_owner = await _register_org(client)
    create_response = await client.post(
        "/api/v1/ai/query", json={"query": "anything"}, headers=_auth_headers(org_a_owner["access_token"])
    )
    task_id = create_response.json()["id"]

    org_b_owner = await _register_org(client)
    response = await client.get(f"/api/v1/ai/tasks/{task_id}", headers=_auth_headers(org_b_owner["access_token"]))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_blank_transcript_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/ai/voice-note", json={"transcript": ""}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_transcript_over_the_length_limit_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/ai/voice-note",
        json={"transcript": "x" * 20_001},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_over_the_length_limit_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/ai/query", json={"query": "x" * 2_001}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_query_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/ai/query", json={"query": ""}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422
