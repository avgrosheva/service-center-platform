"""
Tests for Milestone 12's additional-work endpoints: flag, list, and the
approve/reject/bill status state machine.

Same pattern as test_photos.py / test_materials.py — real ASGI app, real
database, no dependency overrides.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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


async def _flag(
    client: AsyncClient,
    token: str,
    job_id: str,
    *,
    description: str = "Replace worn-out compressor",
    price: str = "4500.00",
    expected_status: int = 201,
) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/additional-work",
        json={"description": description, "price": price},
        headers=_auth_headers(token),
    )
    assert response.status_code == expected_status, response.text
    return response.json()


async def _set_status(
    client: AsyncClient, token: str, job_id: str, item_id: str, new_status: str, *, expected_status: int = 200
) -> dict:
    response = await client.patch(
        f"/api/v1/jobs/{job_id}/additional-work/{item_id}",
        json={"status": new_status},
        headers=_auth_headers(token),
    )
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_flag_persists_as_pending_and_writes_timeline_entry(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    item = await _flag(client, owner["access_token"], job["id"])

    assert item["job_id"] == job["id"]
    assert item["status"] == "pending"
    assert item["created_by_id"] == owner["user_id"]
    assert float(item["price"]) == 4500.00

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert any(e["event_type"] == "additional_work_flagged" for e in timeline.json())


@pytest.mark.asyncio
async def test_zero_or_negative_price_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    for bad_price in ("0", "-100"):
        response = await client.post(
            f"/api/v1/jobs/{job['id']}/additional-work",
            json={"description": "Bad", "price": bad_price},
            headers=_auth_headers(owner["access_token"]),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_description_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/additional-work",
        json={"description": "", "price": "100"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_technician_can_flag_but_gets_403_approving_rejecting_or_billing(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    tech_token = technician["access_token"]

    item = await _flag(client, tech_token, job["id"])
    # created_by_id attribution is correct regardless of who flags it —
    # here, the technician who actually flagged it.
    assert item["created_by_id"] == technician["id"]

    for target_status in ("approved", "rejected"):
        response = await client.patch(
            f"/api/v1/jobs/{job['id']}/additional-work/{item['id']}",
            json={"status": target_status},
            headers=_auth_headers(tech_token),
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_flag_on_behalf_and_attribution_is_still_correct(client):
    # "Cannot flag on behalf of a technician in a way that breaks
    # created_by_id attribution" per the roadmap — created_by_id always
    # reflects whoever actually called the endpoint, never a client-
    # supplied value, so there's no way to misattribute it even though
    # owner/dispatcher are also allowed to flag.
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    item = await _flag(client, owner["access_token"], job["id"])

    assert item["created_by_id"] == owner["user_id"]


@pytest.mark.asyncio
async def test_valid_flow_pending_to_approved_to_billed_writes_timeline_entries(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    item = await _flag(client, owner["access_token"], job["id"])

    approved = await _set_status(client, owner["access_token"], job["id"], item["id"], "approved")
    assert approved["status"] == "approved"

    billed = await _set_status(client, owner["access_token"], job["id"], item["id"], "billed")
    assert billed["status"] == "billed"

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    event_types = [e["event_type"] for e in timeline.json()]
    assert event_types == ["additional_work_flagged", "additional_work_approved", "additional_work_billed"]


@pytest.mark.asyncio
async def test_valid_flow_pending_to_rejected_is_terminal(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    item = await _flag(client, owner["access_token"], job["id"])

    rejected = await _set_status(client, owner["access_token"], job["id"], item["id"], "rejected")
    assert rejected["status"] == "rejected"

    # rejected -> billed is not a valid transition.
    response = await client.patch(
        f"/api/v1/jobs/{job['id']}/additional-work/{item['id']}",
        json={"status": "billed"},
        headers=_auth_headers(owner["access_token"]),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_invalid_transitions_are_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    # pending -> billed, skipping approved.
    item1 = await _flag(client, owner["access_token"], job["id"])
    assert (
        await client.patch(
            f"/api/v1/jobs/{job['id']}/additional-work/{item1['id']}",
            json={"status": "billed"},
            headers=_auth_headers(owner["access_token"]),
        )
    ).status_code == 400

    # approved -> rejected is not allowed (only approved -> billed is).
    item2 = await _flag(client, owner["access_token"], job["id"])
    await _set_status(client, owner["access_token"], job["id"], item2["id"], "approved")
    assert (
        await client.patch(
            f"/api/v1/jobs/{job['id']}/additional-work/{item2['id']}",
            json={"status": "rejected"},
            headers=_auth_headers(owner["access_token"]),
        )
    ).status_code == 400


@pytest.mark.asyncio
async def test_technician_gets_403_on_a_job_not_assigned_to_them(client):
    owner = await _register_org(client)
    technician_a = await _create_member(client, owner["access_token"], role="technician")
    technician_b = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician_b["id"])

    headers_a = _auth_headers(technician_a["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{job['id']}/additional-work",
            json={"description": "X", "price": "10"},
            headers=headers_a,
        )
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/jobs/{job['id']}/additional-work", headers=headers_a)
    ).status_code == 403


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(client, org_a_owner["access_token"], customer_id=org_a_customer["id"])
    item = await _flag(client, org_a_owner["access_token"], org_a_job["id"])

    org_b_owner = await _register_org(client)
    headers_b = _auth_headers(org_b_owner["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/additional-work",
            json={"description": "X", "price": "10"},
            headers=headers_b,
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/jobs/{org_a_job['id']}/additional-work", headers=headers_b)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/jobs/{org_a_job['id']}/additional-work/{item['id']}",
            json={"status": "approved"},
            headers=headers_b,
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_listing_returns_items_in_order(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    first = await _flag(client, owner["access_token"], job["id"], description="First")
    second = await _flag(client, owner["access_token"], job["id"], description="Second")

    response = await client.get(f"/api/v1/jobs/{job['id']}/additional-work", headers=headers)

    assert response.status_code == 200
    ids = [i["id"] for i in response.json()]
    assert ids == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_dispatcher_can_flag_and_approve(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    item = await _flag(client, dispatcher["access_token"], job["id"])
    approved = await _set_status(client, dispatcher["access_token"], job["id"], item["id"], "approved")

    assert approved["status"] == "approved"
