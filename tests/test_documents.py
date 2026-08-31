"""
Integration tests for Milestone 14's document-generation endpoints:
POST /jobs/{id}/documents (trigger, backed by a FastAPI BackgroundTasks
job) and GET /jobs/{id}/documents (list).

Same pattern as test_photos.py — real ASGI app, real database, no
dependency overrides — plus one thing further: with httpx's ASGITransport
(no real network socket), Starlette runs a request's BackgroundTasks
*before* control returns to the client, so by the time `await
client.post(...)` completes here, the document has already been rendered,
uploaded to MinIO, and persisted — no polling/sleep loop needed to
observe it.

Per the explicit instruction not to settle for "a file was created": these
tests download the actual PDF bytes back from MinIO (via
app.storage.s3_client.download_bytes, real network round-trip against the
local MinIO container — no mocking) and extract their text with pypdf to
assert the rendered content genuinely reflects this job's real data
(customer name, reported issue, material name, technician name, timeline
note) — not just that some PDF-shaped bytes landed somewhere.

test_a_failure_during_generation_is_logged_and_does_not_crash_the_request
near the bottom is Milestone 17's testing checklist, exercised directly:
a simulated S3 failure inside the background task must (a) leave the
request/response cycle unaffected, (b) roll back cleanly (no partial
Document row or timeline entry), and (c) leave an observable trace in the
logs — not disappear silently.
"""

import io
import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader

from app.main import app
from app.storage.s3_client import download_bytes


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


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

    return {"id": user_id, "access_token": login.json()["access_token"], "full_name": full_name}


async def _create_customer(client: AsyncClient, token: str, *, full_name: str = "Anna Ivanova") -> dict:
    response = await client.post(
        "/api/v1/customers",
        json={"full_name": full_name, "phone": "+7 999 123-45-67"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_job(client: AsyncClient, token: str, *, customer_id: str, reported_issue: str) -> dict:
    response = await client.post(
        "/api/v1/jobs",
        json={"customer_id": customer_id, "reported_issue": reported_issue, "address": "5 Pushkina St"},
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


async def _add_material(client: AsyncClient, token: str, job_id: str, *, name: str) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/materials",
        json={"name": name, "quantity": "2", "unit_cost": "300.00"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _set_status(client: AsyncClient, token: str, job_id: str, new_status: str, *, note: str) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/status",
        json={"status": new_status, "note": note},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _trigger_document(
    client: AsyncClient, token: str, job_id: str, *, doc_type: str = "job_report", expected_status: int = 202
) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/documents", json={"type": doc_type}, headers=_auth_headers(token)
    )
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_triggering_generation_returns_immediately_and_document_appears(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="Leaking pipe")

    trigger_response = await _trigger_document(client, owner["access_token"], job["id"])
    assert trigger_response == {"status": "accepted", "type": "job_report"}

    list_response = await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)
    assert list_response.status_code == 200
    documents = list_response.json()
    assert len(documents) == 1
    assert documents[0]["job_id"] == job["id"]
    assert documents[0]["type"] == "job_report"
    assert documents[0]["s3_key"].startswith(f"{owner['organization_id']}/jobs/{job['id']}/documents/")
    assert documents[0]["s3_key"].endswith(".pdf")


@pytest.mark.asyncio
async def test_generation_writes_a_timeline_entry(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="Leaking pipe")

    await _trigger_document(client, owner["access_token"], job["id"])

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert any(e["event_type"] == "document_generated" for e in timeline.json())


@pytest.mark.asyncio
async def test_generated_pdf_content_matches_the_jobs_actual_data(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    technician = await _create_member(
        client, owner["access_token"], role="technician", full_name="Sergey Volkov"
    )
    customer = await _create_customer(client, owner["access_token"], full_name="Anna Ivanova")
    job = await _create_job(
        client,
        owner["access_token"],
        customer_id=customer["id"],
        reported_issue="AC unit blowing warm air, compressor making noise",
    )
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    await _add_material(client, owner["access_token"], job["id"], name="Refrigerant R410A")
    await _set_status(
        client, owner["access_token"], job["id"], "en_route", note="Arrived on site, diagnosed the issue"
    )

    await _trigger_document(client, owner["access_token"], job["id"], doc_type="job_report")

    documents = (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)).json()
    assert len(documents) == 1
    s3_key = documents[0]["s3_key"]

    pdf_bytes = download_bytes(s3_key)
    assert pdf_bytes.startswith(b"%PDF")
    text = _extract_pdf_text(pdf_bytes)

    assert "Job Report" in text
    assert "Anna Ivanova" in text
    assert "5 Pushkina St" in text
    assert "AC unit blowing warm air, compressor making noise" in text
    assert "Sergey Volkov" in text
    assert "Refrigerant R410A" in text
    assert "Arrived on site, diagnosed the issue" in text
    assert job["id"] in text


@pytest.mark.asyncio
async def test_repair_certificate_type_is_respected_in_generated_content(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="Fixed boiler")

    await _trigger_document(client, owner["access_token"], job["id"], doc_type="repair_certificate")

    documents = (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)).json()
    assert documents[0]["type"] == "repair_certificate"

    pdf_bytes = download_bytes(documents[0]["s3_key"])
    text = _extract_pdf_text(pdf_bytes)
    assert "Repair Certificate" in text


@pytest.mark.asyncio
async def test_listing_returns_multiple_documents_in_order(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="X")

    await _trigger_document(client, owner["access_token"], job["id"], doc_type="job_report")
    await _trigger_document(client, owner["access_token"], job["id"], doc_type="repair_certificate")

    documents = (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)).json()
    assert len(documents) == 2
    assert [d["type"] for d in documents] == ["job_report", "repair_certificate"]


@pytest.mark.asyncio
async def test_technician_can_trigger_and_list_on_their_own_assigned_job(client):
    owner = await _register_org(client)
    technician = await _create_member(
        client, owner["access_token"], role="technician", full_name="Field Tech"
    )
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="X")
    await _assign(client, owner["access_token"], job["id"], technician["id"])

    await _trigger_document(client, technician["access_token"], job["id"])

    list_response = await client.get(
        f"/api/v1/jobs/{job['id']}/documents", headers=_auth_headers(technician["access_token"])
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


@pytest.mark.asyncio
async def test_technician_gets_403_on_a_job_not_assigned_to_them(client):
    owner = await _register_org(client)
    technician_a = await _create_member(
        client, owner["access_token"], role="technician", full_name="Tech A"
    )
    technician_b = await _create_member(
        client, owner["access_token"], role="technician", full_name="Tech B"
    )
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="X")
    await _assign(client, owner["access_token"], job["id"], technician_b["id"])

    headers_a = _auth_headers(technician_a["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{job['id']}/documents", json={"type": "job_report"}, headers=headers_a
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers_a)).status_code == 403


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(
        client, org_a_owner["access_token"], customer_id=org_a_customer["id"], reported_issue="X"
    )

    org_b_owner = await _register_org(client)
    headers_b = _auth_headers(org_b_owner["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/documents", json={"type": "job_report"}, headers=headers_b
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/jobs/{org_a_job['id']}/documents", headers=headers_b)
    ).status_code == 404


@pytest.mark.asyncio
async def test_a_job_with_no_equipment_no_materials_and_no_technician_still_generates_cleanly(client):
    # Regression guard for the aggregator's None-handling — an early
    # (unassigned, no equipment, no materials) job must still produce a
    # readable PDF, not a 500 from an unguarded None somewhere.
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], reported_issue="Bare-bones job"
    )

    await _trigger_document(client, owner["access_token"], job["id"])

    documents = (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)).json()
    assert len(documents) == 1

    pdf_bytes = download_bytes(documents[0]["s3_key"])
    text = _extract_pdf_text(pdf_bytes)
    assert "Bare-bones job" in text
    assert "Unassigned" in text


@pytest.mark.asyncio
async def test_a_failure_during_generation_is_logged_and_does_not_crash_the_request(client, monkeypatch, caplog):
    def _raise_on_upload(*args, **kwargs):
        raise RuntimeError("simulated S3 upload failure")

    monkeypatch.setattr("app.storage.s3_client.upload_bytes", _raise_on_upload)

    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], reported_issue="X")

    with caplog.at_level(logging.ERROR, logger="app.workers.document_tasks"):
        trigger_response = await _trigger_document(client, owner["access_token"], job["id"])

    # (a) The request/response cycle is unaffected — still a clean 202,
    # even though the background task running within this same call
    # failed partway through.
    assert trigger_response == {"status": "accepted", "type": "job_report"}

    # (b) Rolled back cleanly: no partial Document row, no orphaned
    # timeline entry from the same failed transaction.
    documents = (await client.get(f"/api/v1/jobs/{job['id']}/documents", headers=headers)).json()
    assert documents == []
    timeline = (await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)).json()
    assert not any(e["event_type"] == "document_generated" for e in timeline)

    # (c) Left an observable trace — a background task silently failing
    # with nothing in the logs is exactly what Milestone 17 rules out.
    assert "Document generation failed" in caplog.text
    assert "simulated S3 upload failure" in caplog.text
