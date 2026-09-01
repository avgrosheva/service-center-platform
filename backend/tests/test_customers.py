"""
Tests for Milestone 6's /customers endpoints.

Same pattern as test_auth.py / test_users.py — real ASGI app, real
database, no dependency overrides. Role-gate coverage and cross-org
isolation coverage are kept as separate, dedicated tests (not folded into
one test) — same convention test_users.py established.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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

    return {"access_token": access_token, "organization_id": profile["organization_id"]}


async def _create_member(client: AsyncClient, owner_token: str, *, role: str) -> dict:
    email = _unique_email()
    password = "member-password-1"
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": f"Test {role.title()}", "role": role, "password": password},
        headers=_auth_headers(owner_token),
    )
    assert response.status_code == 201, response.text

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    return {"access_token": login.json()["access_token"]}


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


@pytest.mark.asyncio
async def test_technician_gets_403_on_every_customers_route(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    headers = _auth_headers(technician["access_token"])

    assert (await client.get("/api/v1/customers", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/customers/{customer['id']}", headers=headers)).status_code == 403
    assert (
        await client.post(
            "/api/v1/customers", json={"full_name": "Nope", "phone": "+79991234567"}, headers=headers
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/customers/{customer['id']}", json={"full_name": "Nope"}, headers=headers
        )
    ).status_code == 403
    assert (await client.delete(f"/api/v1/customers/{customer['id']}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_owner_can_perform_full_crud(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    created = await _create_customer(client, owner["access_token"], full_name="Anna Ivanova", phone="+79161234567")
    assert created["is_active"] is True

    list_response = await client.get("/api/v1/customers", headers=headers)
    assert list_response.status_code == 200
    assert any(c["id"] == created["id"] for c in list_response.json())

    detail_response = await client.get(f"/api/v1/customers/{created['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["full_name"] == "Anna Ivanova"

    patch_response = await client.patch(
        f"/api/v1/customers/{created['id']}", json={"notes": "prefers evening visits"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["notes"] == "prefers evening visits"

    delete_response = await client.delete(f"/api/v1/customers/{created['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_dispatcher_can_also_perform_full_crud(client):
    # Unlike the users module (Milestone 5), dispatchers get full write
    # access here per the Technical Blueprint's role table ("Dispatcher:
    # Create/edit jobs, customers, equipment...") — this test locks in
    # that deliberately different role gate for this module.
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    headers = _auth_headers(dispatcher["access_token"])

    created = await _create_customer(client, dispatcher["access_token"])

    patch_response = await client.patch(
        f"/api/v1/customers/{created['id']}", json={"full_name": "Updated Name"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["full_name"] == "Updated Name"

    delete_response = await client.delete(f"/api/v1/customers/{created['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_cross_org_isolation_on_every_customers_route(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])

    headers_a = _auth_headers(org_a_owner["access_token"])

    list_response = await client.get("/api/v1/customers", headers=headers_a)
    assert list_response.status_code == 200
    assert org_b_customer["id"] not in {c["id"] for c in list_response.json()}

    assert (
        await client.get(f"/api/v1/customers/{org_b_customer['id']}", headers=headers_a)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/customers/{org_b_customer['id']}", json={"full_name": "Hijacked"}, headers=headers_a
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/customers/{org_b_customer['id']}", headers=headers_a)
    ).status_code == 404

    # Org B is unaffected by Org A's failed cross-org attempts.
    headers_b = _auth_headers(org_b_owner["access_token"])
    still_there = await client.get(f"/api/v1/customers/{org_b_customer['id']}", headers=headers_b)
    assert still_there.status_code == 200
    assert still_there.json()["full_name"] == org_b_customer["full_name"]
    assert still_there.json()["is_active"] is True


@pytest.mark.asyncio
async def test_search_matches_partial_name_and_partial_phone(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    target = await _create_customer(client, owner["access_token"], full_name="Zoya Kuznetsova", phone="+79261112233")
    await _create_customer(client, owner["access_token"], full_name="Someone Else", phone="+79267778899")

    by_name = await client.get("/api/v1/customers", params={"search": "Kuznets"}, headers=headers)
    assert by_name.status_code == 200
    assert {c["id"] for c in by_name.json()} == {target["id"]}

    by_phone = await client.get("/api/v1/customers", params={"search": "1112233"}, headers=headers)
    assert by_phone.status_code == 200
    assert {c["id"] for c in by_phone.json()} == {target["id"]}


@pytest.mark.asyncio
async def test_archiving_a_customer_soft_deletes_and_excludes_from_default_list(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])

    delete_response = await client.delete(f"/api/v1/customers/{customer['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False

    list_response = await client.get("/api/v1/customers", headers=headers)
    assert customer["id"] not in {c["id"] for c in list_response.json()}

    # The row itself still exists — a future equipment/job record must be
    # able to resolve an archived customer's details, not just make it
    # disappear entirely.
    detail_response = await client.get(f"/api/v1/customers/{customer['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_phone_with_too_few_digits_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/customers",
        json={"full_name": "Bad Phone", "phone": "12-34"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_full_name_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/customers",
        json={"full_name": "", "phone": "+79991234567"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422
