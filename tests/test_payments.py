"""
Tests for Milestone 13's payment endpoints: GET (status) and PUT (upsert).

Same pattern as test_photos.py / test_materials.py / test_additional_work.py
— real ASGI app, real database, no dependency overrides.
"""

import uuid
from datetime import datetime, timezone

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


async def _upsert_payment(
    client: AsyncClient,
    token: str,
    job_id: str,
    *,
    amount: str = "1500.00",
    method: str = "cash",
    status_: str = "unpaid",
    paid_at: str | None = None,
    expected_status: int = 200,
) -> dict:
    payload = {"amount": amount, "method": method, "status": status_}
    if paid_at is not None:
        payload["paid_at"] = paid_at
    response = await client.put(
        f"/api/v1/jobs/{job_id}/payment", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_get_before_any_payment_is_set_returns_404(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    response = await client.get(f"/api/v1/jobs/{job['id']}/payment", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_creates_on_first_call_and_updates_on_second(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    created = await _upsert_payment(client, owner["access_token"], job["id"], amount="1000.00", method="cash")
    assert created["job_id"] == job["id"]
    assert float(created["amount"]) == 1000.00
    assert created["method"] == "cash"
    assert created["status"] == "unpaid"

    updated = await _upsert_payment(client, owner["access_token"], job["id"], amount="1200.00", method="card")
    assert updated["id"] == created["id"]
    assert float(updated["amount"]) == 1200.00
    assert updated["method"] == "card"

    get_response = await client.get(f"/api/v1/jobs/{job['id']}/payment", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]
    assert float(get_response.json()["amount"]) == 1200.00


@pytest.mark.asyncio
async def test_setting_status_paid_without_paid_at_autopopulates_it(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    before = datetime.now(timezone.utc)
    payment = await _upsert_payment(client, owner["access_token"], job["id"], status_="paid")
    after = datetime.now(timezone.utc)

    assert payment["status"] == "paid"
    assert payment["paid_at"] is not None
    paid_at = datetime.fromisoformat(payment["paid_at"])
    assert before <= paid_at <= after


@pytest.mark.asyncio
async def test_explicit_paid_at_is_respected_not_overridden(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    backdated = "2026-01-15T10:00:00Z"
    payment = await _upsert_payment(client, owner["access_token"], job["id"], status_="paid", paid_at=backdated)

    assert payment["paid_at"].startswith("2026-01-15T10:00:00")


@pytest.mark.asyncio
async def test_zero_or_negative_amount_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    for bad_amount in ("0", "-50"):
        response = await client.put(
            f"/api/v1/jobs/{job['id']}/payment",
            json={"amount": bad_amount, "method": "cash", "status": "unpaid"},
            headers=_auth_headers(owner["access_token"]),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_technician_is_blocked_entirely(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _upsert_payment(client, owner["access_token"], job["id"])

    headers = _auth_headers(technician["access_token"])

    assert (await client.get(f"/api/v1/jobs/{job['id']}/payment", headers=headers)).status_code == 403
    assert (
        await client.put(
            f"/api/v1/jobs/{job['id']}/payment",
            json={"amount": "100", "method": "cash", "status": "unpaid"},
            headers=headers,
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_technician_is_blocked_even_on_their_own_assigned_job(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    assign_response = await client.post(
        f"/api/v1/jobs/{job['id']}/assign",
        json={"technician_id": technician["id"]},
        headers=_auth_headers(owner["access_token"]),
    )
    assert assign_response.status_code == 200

    response = await client.get(
        f"/api/v1/jobs/{job['id']}/payment", headers=_auth_headers(technician["access_token"])
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_dispatcher_can_manage_payment(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    payment = await _upsert_payment(client, dispatcher["access_token"], job["id"])

    assert payment["job_id"] == job["id"]


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(client, org_a_owner["access_token"], customer_id=org_a_customer["id"])
    await _upsert_payment(client, org_a_owner["access_token"], org_a_job["id"])

    org_b_owner = await _register_org(client)
    headers_b = _auth_headers(org_b_owner["access_token"])

    assert (await client.get(f"/api/v1/jobs/{org_a_job['id']}/payment", headers=headers_b)).status_code == 404
    assert (
        await client.put(
            f"/api/v1/jobs/{org_a_job['id']}/payment",
            json={"amount": "100", "method": "cash", "status": "unpaid"},
            headers=headers_b,
        )
    ).status_code == 404
