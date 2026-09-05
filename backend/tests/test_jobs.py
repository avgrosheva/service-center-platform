"""
Tests for /jobs: Milestone 8's creation/listing/detail/editable-field
update/soft-cancellation, Milestone 9's assignment/validated status
transitions/timeline/technician scoping, and Milestone 15's warranty
auto-flagging on job creation.

Same pattern as test_customers.py / test_equipment.py — real ASGI app,
real database, no dependency overrides.

test_updating_equipment_address_does_not_retroactively_change_existing_job_snapshot
below is the address-snapshot invariant test flagged as required back in
Milestone 7: the frozen address model's core guarantee is that
`jobs.address_snapshot` is a one-time copy taken at job-creation time, and
a later edit to `equipment.installation_address` must never reach back and
change it on a job that already exists.

The Milestone 15 tests near the bottom of this file backdate a completed
job's `warranty_expires_at` via a direct DB session (same pattern as
test_models.py) rather than through the API — there's no endpoint that
lets a caller set an arbitrary warranty expiry date (it's always
`completed_at + DEFAULT_WARRANTY_DAYS`), so exercising the "warranty
already expired" and exact-boundary cases requires reaching past the API
for setup, same as any other test that needs to arrange state the product
itself would never produce through normal use.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.job import Job


def _unique_email() -> str:
    # See test_auth.py: email-validator rejects the .test TLD as reserved.
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


async def _create_customer(
    client: AsyncClient, token: str, *, full_name: str = "Ivan Petrov", phone: str = "+7 999 123-45-67"
) -> dict:
    response = await client.post(
        "/api/v1/customers",
        json={"full_name": full_name, "phone": phone},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_equipment(
    client: AsyncClient,
    token: str,
    customer_id: str,
    *,
    type_: str = "AC",
    installation_address: str = "12 Lenina St, Apt 5",
) -> dict:
    response = await client.post(
        f"/api/v1/customers/{customer_id}/equipment",
        json={"type": type_, "installation_address": installation_address},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_job(
    client: AsyncClient,
    token: str,
    *,
    customer_id: str,
    equipment_id: str | None = None,
    reported_issue: str = "AC not cooling",
    address: str | None = None,
    scheduled_at: str | None = None,
    is_warranty_claim: bool | None = None,
    expected_status: int = 201,
) -> dict:
    payload = {"customer_id": customer_id, "reported_issue": reported_issue}
    if equipment_id is not None:
        payload["equipment_id"] = equipment_id
    if address is not None:
        payload["address"] = address
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at
    if is_warranty_claim is not None:
        payload["is_warranty_claim"] = is_warranty_claim

    response = await client.post("/api/v1/jobs", json=payload, headers=_auth_headers(token))
    assert response.status_code == expected_status, response.text
    return response.json()


async def _assign(
    client: AsyncClient, token: str, job_id: str, technician_id: str, *, expected_status: int = 200
) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/assign",
        json={"technician_id": technician_id},
        headers=_auth_headers(token),
    )
    assert response.status_code == expected_status, response.text
    return response.json()


async def _set_status(
    client: AsyncClient, token: str, job_id: str, new_status: str, *, note: str | None = None, expected_status: int = 200
) -> dict:
    payload = {"status": new_status}
    if note is not None:
        payload["note"] = note
    response = await client.post(
        f"/api/v1/jobs/{job_id}/status", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == expected_status, response.text
    return response.json()


async def _complete_job(client: AsyncClient, owner_token: str, job_id: str, technician_id: str) -> dict:
    """Walks a fresh job through assign -> en_route -> in_progress -> awaiting_approval -> completed."""
    await _assign(client, owner_token, job_id, technician_id)
    await _set_status(client, owner_token, job_id, "en_route")
    await _set_status(client, owner_token, job_id, "in_progress")
    await _set_status(client, owner_token, job_id, "awaiting_approval")
    return await _set_status(client, owner_token, job_id, "completed")


@pytest.mark.asyncio
async def test_job_creation_with_equipment_snapshots_the_current_address(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(
        client, owner["access_token"], customer["id"], installation_address="5 Pushkina St"
    )

    job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )

    assert job["equipment_id"] == equipment["id"]
    assert job["address_snapshot"] == "5 Pushkina St"
    assert job["status"] == "new"
    assert job["created_by_id"] == owner["user_id"]
    assert job["assigned_technician_id"] is None


@pytest.mark.asyncio
async def test_job_creation_without_equipment_accepts_manual_address(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], address="Manually entered address"
    )

    assert job["equipment_id"] is None
    assert job["address_snapshot"] == "Manually entered address"


@pytest.mark.asyncio
async def test_job_creation_without_equipment_or_address_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    response = await client.post(
        "/api/v1/jobs",
        json={"customer_id": customer["id"], "reported_issue": "Leaking"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_updating_equipment_address_does_not_retroactively_change_existing_job_snapshot(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(
        client, owner["access_token"], customer["id"], installation_address="Original address"
    )

    job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    assert job["address_snapshot"] == "Original address"

    patch_response = await client.patch(
        f"/api/v1/equipment/{equipment['id']}",
        json={"installation_address": "New address after move"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["installation_address"] == "New address after move"

    # The existing job's snapshot must stay frozen at what it was when the
    # job was created — this is the whole point of "snapshot."
    refetched_job = await client.get(f"/api/v1/jobs/{job['id']}", headers=headers)
    assert refetched_job.status_code == 200
    assert refetched_job.json()["address_snapshot"] == "Original address"

    # A NEW job created against the same (now-updated) equipment picks up
    # the current address — proving the old job's frozen value isn't a
    # caching bug, and the mechanism genuinely re-reads at creation time.
    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    assert new_job["address_snapshot"] == "New address after move"


@pytest.mark.asyncio
async def test_technician_still_blocked_from_create_update_assign_and_cancel(client):
    # These stay owner/dispatcher-only per the Technical Blueprint's role
    # table — none of them are part of a technician's role, even on their
    # own assigned job.
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    headers = _auth_headers(technician["access_token"])

    assert (
        await client.post(
            "/api/v1/jobs",
            json={"customer_id": customer["id"], "reported_issue": "Nope", "address": "Nowhere"},
            headers=headers,
        )
    ).status_code == 403
    assert (
        await client.patch(f"/api/v1/jobs/{job['id']}", json={"reported_issue": "Nope"}, headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/jobs/{job['id']}", headers=headers)).status_code == 403
    assert (
        await client.post(
            f"/api/v1/jobs/{job['id']}/assign", json={"technician_id": technician["id"]}, headers=headers
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_technician_can_view_and_transition_their_own_assigned_job(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    headers = _auth_headers(technician["access_token"])

    list_response = await client.get("/api/v1/jobs", headers=headers)
    assert list_response.status_code == 200
    assert {j["id"] for j in list_response.json()} == {job["id"]}

    detail_response = await client.get(f"/api/v1/jobs/{job['id']}", headers=headers)
    assert detail_response.status_code == 200

    status_response = await client.post(
        f"/api/v1/jobs/{job['id']}/status", json={"status": "en_route"}, headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "en_route"

    timeline_response = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline_response.status_code == 200
    assert any(e["event_type"] == "status_changed" and e["to_status"] == "en_route" for e in timeline_response.json())


@pytest.mark.asyncio
async def test_technician_gets_403_on_a_job_not_assigned_to_them(client):
    owner = await _register_org(client)
    owner_headers = _auth_headers(owner["access_token"])
    technician_a = await _create_member(client, owner["access_token"], role="technician")
    technician_b = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])

    unassigned_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], address="Unassigned"
    )
    other_job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Other")
    await _assign(client, owner["access_token"], other_job["id"], technician_b["id"])

    headers_a = _auth_headers(technician_a["access_token"])

    # Neither an unassigned job nor another technician's job is visible.
    list_response = await client.get("/api/v1/jobs", headers=headers_a)
    assert list_response.status_code == 200
    assert list_response.json() == []

    for target in (unassigned_job, other_job):
        assert (await client.get(f"/api/v1/jobs/{target['id']}", headers=headers_a)).status_code == 403
        assert (
            await client.post(
                f"/api/v1/jobs/{target['id']}/status", json={"status": "en_route"}, headers=headers_a
            )
        ).status_code == 403
        assert (
            await client.get(f"/api/v1/jobs/{target['id']}/timeline", headers=headers_a)
        ).status_code == 403


@pytest.mark.asyncio
async def test_technician_gets_404_not_403_on_a_job_from_a_different_organization(client):
    # Distinct from the "same-org, not-my-job" case above, which is 403.
    # A cross-org job_id must come back exactly like the tenant-isolation
    # convention Milestone 5 established for owner/dispatcher: 404, not
    # 403 — a 403 would leak the fact that the id belongs to *some* job
    # somewhere, whereas 404 is indistinguishable from an id that was
    # never issued at all. job_service enforces this by scoping the
    # existence lookup to the caller's own organization_id before the
    # technician-ownership check ever runs, so a cross-org id is simply
    # "not found," never reached as "found but not yours."
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(
        client, org_a_owner["access_token"], customer_id=org_a_customer["id"], address="Org A job"
    )

    org_b_owner = await _register_org(client)
    org_b_technician = await _create_member(client, org_b_owner["access_token"], role="technician")
    headers_b_tech = _auth_headers(org_b_technician["access_token"])

    list_response = await client.get("/api/v1/jobs", headers=headers_b_tech)
    assert list_response.status_code == 200
    assert org_a_job["id"] not in {j["id"] for j in list_response.json()}

    assert (await client.get(f"/api/v1/jobs/{org_a_job['id']}", headers=headers_b_tech)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/status", json={"status": "en_route"}, headers=headers_b_tech
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/jobs/{org_a_job['id']}/timeline", headers=headers_b_tech)
    ).status_code == 404


@pytest.mark.asyncio
async def test_dispatcher_can_also_perform_full_crud(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])

    job = await _create_job(
        client, dispatcher["access_token"], customer_id=customer["id"], address="Dispatcher-created address"
    )

    patch_response = await client.patch(
        f"/api/v1/jobs/{job['id']}",
        json={"reported_issue": "Updated issue"},
        headers=_auth_headers(dispatcher["access_token"]),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["reported_issue"] == "Updated issue"

    delete_response = await client.delete(
        f"/api/v1/jobs/{job['id']}", headers=_auth_headers(dispatcher["access_token"])
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cross_org_isolation_on_every_jobs_route(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])
    org_b_job = await _create_job(
        client, org_b_owner["access_token"], customer_id=org_b_customer["id"], address="Org B address"
    )

    headers_a = _auth_headers(org_a_owner["access_token"])

    list_response = await client.get("/api/v1/jobs", headers=headers_a)
    assert list_response.status_code == 200
    assert org_b_job["id"] not in {j["id"] for j in list_response.json()}

    assert (await client.get(f"/api/v1/jobs/{org_b_job['id']}", headers=headers_a)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/jobs/{org_b_job['id']}", json={"reported_issue": "Hijacked"}, headers=headers_a
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/jobs/{org_b_job['id']}", headers=headers_a)).status_code == 404

    # Org B is unaffected by Org A's failed cross-org attempts.
    headers_b = _auth_headers(org_b_owner["access_token"])
    still_there = await client.get(f"/api/v1/jobs/{org_b_job['id']}", headers=headers_b)
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "new"


@pytest.mark.asyncio
async def test_creating_job_with_customer_from_a_different_org_is_rejected(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])

    response = await client.post(
        "/api/v1/jobs",
        json={"customer_id": org_b_customer["id"], "reported_issue": "Nope", "address": "Nowhere"},
        headers=_auth_headers(org_a_owner["access_token"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_creating_job_with_equipment_from_a_different_org_is_rejected(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])
    org_b_equipment = await _create_equipment(client, org_b_owner["access_token"], org_b_customer["id"])

    response = await client.post(
        "/api/v1/jobs",
        json={
            "customer_id": org_a_customer["id"],
            "equipment_id": org_b_equipment["id"],
            "reported_issue": "Nope",
        },
        headers=_auth_headers(org_a_owner["access_token"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_creating_job_with_equipment_belonging_to_a_different_customer_is_rejected(client):
    owner = await _register_org(client)
    customer_a = await _create_customer(client, owner["access_token"], full_name="Customer A")
    customer_b = await _create_customer(client, owner["access_token"], full_name="Customer B")
    equipment_of_b = await _create_equipment(client, owner["access_token"], customer_b["id"])

    response = await client.post(
        "/api/v1/jobs",
        json={
            "customer_id": customer_a["id"],
            "equipment_id": equipment_of_b["id"],
            "reported_issue": "Mismatched",
        },
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reported_issue_is_required(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    response = await client.post(
        "/api/v1/jobs",
        json={"customer_id": customer["id"], "reported_issue": "", "address": "Somewhere"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_filters_by_status(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    new_job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="A")
    cancelled_job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="B")
    cancel_response = await client.delete(f"/api/v1/jobs/{cancelled_job['id']}", headers=headers)
    assert cancel_response.status_code == 200

    new_list = await client.get("/api/v1/jobs", params={"status": "new"}, headers=headers)
    assert new_list.status_code == 200
    new_ids = {j["id"] for j in new_list.json()}
    assert new_job["id"] in new_ids
    assert cancelled_job["id"] not in new_ids

    cancelled_list = await client.get("/api/v1/jobs", params={"status": "cancelled"}, headers=headers)
    assert cancelled_list.status_code == 200
    cancelled_ids = {j["id"] for j in cancelled_list.json()}
    assert cancelled_job["id"] in cancelled_ids
    assert new_job["id"] not in cancelled_ids


@pytest.mark.asyncio
async def test_list_filters_by_scheduled_date_range(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    early_job = await _create_job(
        client,
        owner["access_token"],
        customer_id=customer["id"],
        address="Early",
        scheduled_at="2026-01-10T09:00:00Z",
    )
    late_job = await _create_job(
        client,
        owner["access_token"],
        customer_id=customer["id"],
        address="Late",
        scheduled_at="2026-03-10T09:00:00Z",
    )

    response = await client.get(
        "/api/v1/jobs",
        params={"scheduled_from": "2026-02-01T00:00:00Z", "scheduled_to": "2026-04-01T00:00:00Z"},
        headers=headers,
    )
    assert response.status_code == 200
    ids = {j["id"] for j in response.json()}
    assert late_job["id"] in ids
    assert early_job["id"] not in ids


@pytest.mark.asyncio
async def test_owner_list_filters_by_assigned_technician(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    assigned_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], address="Assigned"
    )
    await _assign(client, owner["access_token"], assigned_job["id"], technician["id"])
    await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Unassigned")

    response = await client.get(
        "/api/v1/jobs", params={"assigned_technician_id": technician["id"]}, headers=headers
    )

    assert response.status_code == 200
    assert {j["id"] for j in response.json()} == {assigned_job["id"]}


@pytest.mark.asyncio
async def test_list_filters_by_customer_id(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer_a = await _create_customer(client, owner["access_token"], full_name="Customer A")
    customer_b = await _create_customer(client, owner["access_token"], full_name="Customer B")
    job_a = await _create_job(client, owner["access_token"], customer_id=customer_a["id"], address="A")
    await _create_job(client, owner["access_token"], customer_id=customer_b["id"], address="B")

    response = await client.get(
        "/api/v1/jobs", params={"customer_id": customer_a["id"]}, headers=headers
    )

    assert response.status_code == 200
    assert {j["id"] for j in response.json()} == {job_a["id"]}


@pytest.mark.asyncio
async def test_list_filters_by_equipment_id(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    equipment_a = await _create_equipment(client, owner["access_token"], customer["id"])
    equipment_b = await _create_equipment(client, owner["access_token"], customer["id"])
    job_a = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment_a["id"]
    )
    await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment_b["id"]
    )

    response = await client.get(
        "/api/v1/jobs", params={"equipment_id": equipment_a["id"]}, headers=headers
    )

    assert response.status_code == 200
    assert {j["id"] for j in response.json()} == {job_a["id"]}


@pytest.mark.asyncio
async def test_patch_updates_editable_fields_but_not_status(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Old address")

    response = await client.patch(
        f"/api/v1/jobs/{job['id']}",
        json={
            "reported_issue": "Updated issue",
            "address_snapshot": "Corrected address",
            "scheduled_at": "2026-05-01T10:00:00Z",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reported_issue"] == "Updated issue"
    assert body["address_snapshot"] == "Corrected address"
    assert body["scheduled_at"] is not None
    assert body["status"] == "new"


@pytest.mark.asyncio
async def test_delete_soft_cancels_without_hard_deleting(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")

    delete_response = await client.delete(f"/api/v1/jobs/{job['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "cancelled"

    # The row still exists and is reachable — this is a status change, not
    # a hard delete.
    detail_response = await client.get(f"/api/v1/jobs/{job['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_assign_sets_technician_transitions_to_assigned_and_writes_timeline_entry(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")

    assigned = await _assign(client, owner["access_token"], job["id"], technician["id"])

    assert assigned["assigned_technician_id"] == technician["id"]
    assert assigned["status"] == "assigned"

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    entries = timeline.json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "assigned"
    assert entries[0]["from_status"] == "new"
    assert entries[0]["to_status"] == "assigned"
    assert entries[0]["actor_id"] == owner["user_id"]


@pytest.mark.asyncio
async def test_assign_rejects_a_non_technician_user(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/assign",
        json={"technician_id": dispatcher["id"]},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_assign_rejects_an_inactive_technician(client):
    owner = await _register_org(client)
    owner_headers = _auth_headers(owner["access_token"])
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")

    deactivate = await client.delete(f"/api/v1/users/{technician['id']}", headers=owner_headers)
    assert deactivate.status_code == 200

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/assign",
        json={"technician_id": technician["id"]},
        headers=owner_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_assign_rejects_a_technician_from_a_different_organization(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(
        client, org_a_owner["access_token"], customer_id=org_a_customer["id"], address="Somewhere"
    )
    org_b_owner = await _register_org(client)
    org_b_technician = await _create_member(client, org_b_owner["access_token"], role="technician")

    response = await client.post(
        f"/api/v1/jobs/{org_a_job['id']}/assign",
        json={"technician_id": org_b_technician["id"]},
        headers=_auth_headers(org_a_owner["access_token"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_assign_rejects_a_job_not_currently_in_new_status(client):
    owner = await _register_org(client)
    technician_a = await _create_member(client, owner["access_token"], role="technician")
    technician_b = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")
    await _assign(client, owner["access_token"], job["id"], technician_a["id"])

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/assign",
        json={"technician_id": technician_b["id"]},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_valid_status_transition_chain_succeeds_and_completion_sets_dates(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")
    await _assign(client, owner["access_token"], job["id"], technician["id"])

    for target in ("en_route", "in_progress", "awaiting_parts", "in_progress", "awaiting_approval", "completed"):
        updated = await _set_status(client, owner["access_token"], job["id"], target)
        assert updated["status"] == target

    assert updated["completed_at"] is not None
    assert updated["warranty_expires_at"] is not None

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    entries = timeline.json()
    # One "assigned" entry from _assign, plus one "status_changed" entry
    # per _set_status call above.
    assert len(entries) == 7
    status_changed_entries = [e for e in entries if e["event_type"] == "status_changed"]
    assert [e["to_status"] for e in status_changed_entries] == [
        "en_route",
        "in_progress",
        "awaiting_parts",
        "in_progress",
        "awaiting_approval",
        "completed",
    ]
    # Chronological order, oldest first.
    created_ats = [e["created_at"] for e in entries]
    assert created_ats == sorted(created_ats)


@pytest.mark.asyncio
async def test_invalid_status_transition_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="Somewhere")

    # new -> completed is not a valid direct transition.
    response = await client.post(
        f"/api/v1/jobs/{job['id']}/status",
        json={"status": "completed"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cancelled_is_reachable_from_any_non_terminal_state(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])

    # new -> cancelled
    job1 = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="A")
    await _set_status(client, owner["access_token"], job1["id"], "cancelled")

    # assigned -> cancelled
    job2 = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="B")
    await _assign(client, owner["access_token"], job2["id"], technician["id"])
    await _set_status(client, owner["access_token"], job2["id"], "cancelled")

    # in_progress -> cancelled
    job3 = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="C")
    await _assign(client, owner["access_token"], job3["id"], technician["id"])
    await _set_status(client, owner["access_token"], job3["id"], "en_route")
    await _set_status(client, owner["access_token"], job3["id"], "in_progress")
    cancelled = await _set_status(client, owner["access_token"], job3["id"], "cancelled")
    assert cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_transition_out_of_a_terminal_state(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    cancelled_job = await _create_job(client, owner["access_token"], customer_id=customer["id"], address="A")
    await _set_status(client, owner["access_token"], cancelled_job["id"], "cancelled")

    response = await client.post(
        f"/api/v1/jobs/{cancelled_job['id']}/status",
        json={"status": "assigned"},
        headers=_auth_headers(owner["access_token"]),
    )
    assert response.status_code == 400

    # Cancelling an already-cancelled job is also rejected — this is the
    # concrete regression the roadmap's own transition table (rather than
    # Milestone 8's unconditional overwrite) exists to prevent.
    redelete = await client.delete(f"/api/v1/jobs/{cancelled_job['id']}", headers=_auth_headers(owner["access_token"]))
    assert redelete.status_code == 400


async def _set_warranty_expires_at(job_id: str, expires_at: date) -> None:
    """Directly backdates a job's warranty_expires_at — see the module docstring for why."""
    async with AsyncSessionLocal() as session:
        job = (await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))).scalar_one()
        job.warranty_expires_at = expires_at
        await session.commit()


def _utc_today() -> date:
    """
    The backend's own warranty comparison (job_service._find_active_warranty_origin)
    computes "today" as `datetime.now(timezone.utc).date()`, not local
    system time. These boundary tests must use the exact same basis —
    plain `date.today()` reads the test-runner machine's LOCAL calendar
    date, which silently diverges from the backend's UTC date for a few
    hours around any local-midnight/UTC-midnight mismatch (e.g. UTC+3:
    local rolls to a new day three hours before UTC does). Within that
    window, "yesterday" computed locally can equal "today" in UTC,
    flipping these boundary assertions — exactly what broke here once,
    caught by the daily test run crossing that window, not by a flaw in
    the backend's own (UTC-consistent, correct) logic.
    """
    return datetime.now(timezone.utc).date()


@pytest.mark.asyncio
async def test_new_job_on_equipment_with_active_warranty_auto_flags_and_links_origin(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    completed = await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])
    assert completed["warranty_expires_at"] is not None  # set by Milestone 9's completion logic; still in the future

    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )

    assert new_job["is_warranty_claim"] is True
    assert new_job["origin_job_id"] == origin_job["id"]


@pytest.mark.asyncio
async def test_new_job_on_equipment_past_warranty_window_does_not_auto_flag(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])
    await _set_warranty_expires_at(origin_job["id"], _utc_today() - timedelta(days=1))

    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )

    assert new_job["is_warranty_claim"] is False
    assert new_job["origin_job_id"] is None


@pytest.mark.asyncio
async def test_warranty_boundary_exactly_on_expiry_date_still_counts(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])
    await _set_warranty_expires_at(origin_job["id"], _utc_today())

    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )

    assert new_job["is_warranty_claim"] is True
    assert new_job["origin_job_id"] == origin_job["id"]


@pytest.mark.asyncio
async def test_warranty_boundary_one_day_after_expiry_does_not_count(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])
    await _set_warranty_expires_at(origin_job["id"], _utc_today() - timedelta(days=1))

    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )

    assert new_job["is_warranty_claim"] is False


@pytest.mark.asyncio
async def test_manual_override_forces_warranty_claim_true_even_without_a_match(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])
    # Fresh equipment: no prior completed job at all, so auto-detection
    # has nothing to find.

    job = await _create_job(
        client,
        owner["access_token"],
        customer_id=customer["id"],
        equipment_id=equipment["id"],
        is_warranty_claim=True,
    )

    assert job["is_warranty_claim"] is True
    assert job["origin_job_id"] is None  # forced true, but nothing real to link — never fabricated


@pytest.mark.asyncio
async def test_manual_override_forces_warranty_claim_false_despite_active_warranty(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])

    new_job = await _create_job(
        client,
        owner["access_token"],
        customer_id=customer["id"],
        equipment_id=equipment["id"],
        is_warranty_claim=False,
    )

    assert new_job["is_warranty_claim"] is False
    assert new_job["origin_job_id"] is None


@pytest.mark.asyncio
async def test_warranty_auto_flag_only_considers_the_same_equipment(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment_a = await _create_equipment(client, owner["access_token"], customer["id"])
    equipment_b = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment_a["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])

    # Same customer, different equipment — no warranty link should apply.
    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment_b["id"]
    )

    assert new_job["is_warranty_claim"] is False
    assert new_job["origin_job_id"] is None


@pytest.mark.asyncio
async def test_warranty_auto_flag_does_not_apply_without_equipment_id(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])

    origin_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], equipment_id=equipment["id"]
    )
    await _complete_job(client, owner["access_token"], origin_job["id"], technician["id"])

    # Same customer, no equipment_id this time — auto-detection is
    # equipment-keyed, so it has nothing to search against.
    new_job = await _create_job(
        client, owner["access_token"], customer_id=customer["id"], address="A different address entirely"
    )

    assert new_job["is_warranty_claim"] is False
    assert new_job["origin_job_id"] is None
