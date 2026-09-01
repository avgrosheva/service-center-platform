"""
Tests for Milestone 7's /equipment endpoints.

Same pattern as test_customers.py / test_users.py — real ASGI app, real
database, no dependency overrides.

Note on the address-snapshot invariant: the frozen address model (Technical
Blueprint, Section 3) requires that editing `equipment.installation_address`
never retroactively changes `jobs.address_snapshot` on a job already
created against this equipment. That specific regression test cannot exist
yet — `jobs` doesn't exist until Milestone 8 — so it isn't here. It belongs
in test_jobs.py once Job/address_snapshot land, exercising exactly the
PATCH /equipment/{id} endpoint below.
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


async def _create_equipment(
    client: AsyncClient,
    token: str,
    customer_id: str,
    *,
    type_: str = "AC",
    installation_address: str = "12 Lenina St, Apt 5",
    **extra,
) -> dict:
    payload = {"type": type_, "installation_address": installation_address, **extra}
    response = await client.post(
        f"/api/v1/customers/{customer_id}/equipment",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_technician_gets_403_on_every_equipment_route(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(client, owner["access_token"], customer["id"])
    headers = _auth_headers(technician["access_token"])

    assert (
        await client.get(f"/api/v1/customers/{customer['id']}/equipment", headers=headers)
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/customers/{customer['id']}/equipment",
            json={"type": "fridge", "installation_address": "somewhere"},
            headers=headers,
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/equipment/{equipment['id']}", headers=headers)).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/equipment/{equipment['id']}", json={"brand": "Nope"}, headers=headers
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_owner_can_perform_full_crud(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])

    created = await _create_equipment(
        client,
        owner["access_token"],
        customer["id"],
        type_="refrigerator",
        brand="LG",
        model="GR-X247",
        serial_number="SN-001",
        installation_address="5 Pushkina St",
        install_date="2024-01-15",
        warranty_until="2026-01-15",
    )
    assert created["customer_id"] == customer["id"]
    assert created["brand"] == "LG"

    list_response = await client.get(f"/api/v1/customers/{customer['id']}/equipment", headers=headers)
    assert list_response.status_code == 200
    assert any(e["id"] == created["id"] for e in list_response.json())

    detail_response = await client.get(f"/api/v1/equipment/{created['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["serial_number"] == "SN-001"

    patch_response = await client.patch(
        f"/api/v1/equipment/{created['id']}", json={"brand": "Samsung"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["brand"] == "Samsung"


@pytest.mark.asyncio
async def test_dispatcher_can_also_perform_full_crud(client):
    # Same deliberately-full role gate as customers (Milestone 6): per the
    # Technical Blueprint's role table, dispatchers create/edit equipment.
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])

    created = await _create_equipment(client, dispatcher["access_token"], customer["id"])

    patch_response = await client.patch(
        f"/api/v1/equipment/{created['id']}",
        json={"installation_address": "Updated address"},
        headers=_auth_headers(dispatcher["access_token"]),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["installation_address"] == "Updated address"


@pytest.mark.asyncio
async def test_cross_org_isolation_on_every_equipment_route(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])
    org_b_equipment = await _create_equipment(client, org_b_owner["access_token"], org_b_customer["id"])

    headers_a = _auth_headers(org_a_owner["access_token"])

    # Org A can't even list equipment under Org B's customer.
    assert (
        await client.get(f"/api/v1/customers/{org_b_customer['id']}/equipment", headers=headers_a)
    ).status_code == 404

    # Org A can't view or update Org B's equipment directly by id.
    assert (
        await client.get(f"/api/v1/equipment/{org_b_equipment['id']}", headers=headers_a)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/equipment/{org_b_equipment['id']}", json={"brand": "Hijacked"}, headers=headers_a
        )
    ).status_code == 404

    # Org B is unaffected by Org A's failed cross-org attempts.
    headers_b = _auth_headers(org_b_owner["access_token"])
    still_there = await client.get(f"/api/v1/equipment/{org_b_equipment['id']}", headers=headers_b)
    assert still_there.status_code == 200
    assert still_there.json()["brand"] != "Hijacked"


@pytest.mark.asyncio
async def test_creating_equipment_under_a_customer_from_a_different_org_is_rejected(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_customer = await _create_customer(client, org_b_owner["access_token"])

    response = await client.post(
        f"/api/v1/customers/{org_b_customer['id']}/equipment",
        json={"type": "boiler", "installation_address": "Nice try"},
        headers=_auth_headers(org_a_owner["access_token"]),
    )

    assert response.status_code == 404

    # And Org B's own view of its customer's equipment is untouched.
    list_response = await client.get(
        f"/api/v1/customers/{org_b_customer['id']}/equipment",
        headers=_auth_headers(org_b_owner["access_token"]),
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_creating_equipment_under_a_nonexistent_customer_is_rejected(client):
    owner = await _register_org(client)

    response = await client.post(
        f"/api/v1/customers/{uuid.uuid4()}/equipment",
        json={"type": "boiler", "installation_address": "Nowhere"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_serial_number_and_optional_fields_are_not_required(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/equipment",
        json={"type": "washing machine", "installation_address": "Somewhere"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["serial_number"] is None
    assert body["brand"] is None
    assert body["model"] is None
    assert body["install_date"] is None
    assert body["warranty_until"] is None


@pytest.mark.asyncio
async def test_blank_type_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/equipment",
        json={"type": "", "installation_address": "Somewhere"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_installation_address_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])

    response = await client.post(
        f"/api/v1/customers/{customer['id']}/equipment",
        json={"type": "AC", "installation_address": ""},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_updating_installation_address_persists_the_new_value(client):
    # This is the non-Job half of the frozen address-model invariant: the
    # equipment record itself is freely mutable. The other half (that this
    # update must NOT retroactively change any existing job's
    # address_snapshot) can only be tested once Job exists in Milestone 8.
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    equipment = await _create_equipment(
        client, owner["access_token"], customer["id"], installation_address="Old address"
    )

    response = await client.patch(
        f"/api/v1/equipment/{equipment['id']}",
        json={"installation_address": "New address"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["installation_address"] == "New address"

    refetched = await client.get(
        f"/api/v1/equipment/{equipment['id']}", headers=_auth_headers(owner["access_token"])
    )
    assert refetched.json()["installation_address"] == "New address"
