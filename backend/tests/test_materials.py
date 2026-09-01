"""
Tests for Milestone 11's material endpoints: add, list, edit, remove.

Same pattern as test_photos.py — real ASGI app, real database, no
dependency overrides.
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


async def _add_material(
    client: AsyncClient,
    token: str,
    job_id: str,
    *,
    name: str = "Refrigerant R410A",
    quantity: str = "2.5",
    unit_cost: str | None = "1500.00",
    expected_status: int = 201,
) -> dict:
    payload = {"name": name, "quantity": quantity}
    if unit_cost is not None:
        payload["unit_cost"] = unit_cost
    response = await client.post(
        f"/api/v1/jobs/{job_id}/materials", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_add_material_persists_and_writes_timeline_entry(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    material = await _add_material(client, owner["access_token"], job["id"])

    assert material["job_id"] == job["id"]
    assert material["name"] == "Refrigerant R410A"
    assert float(material["quantity"]) == 2.5
    assert float(material["unit_cost"]) == 1500.00

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert any(e["event_type"] == "material_added" for e in timeline.json())


@pytest.mark.asyncio
async def test_zero_or_negative_quantity_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    for bad_quantity in ("0", "-1"):
        response = await client.post(
            f"/api/v1/jobs/{job['id']}/materials",
            json={"name": "Bad", "quantity": bad_quantity},
            headers=_auth_headers(owner["access_token"]),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_negative_unit_cost_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/materials",
        json={"name": "Bad", "quantity": "1", "unit_cost": "-5"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unit_cost_is_optional(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    material = await _add_material(client, owner["access_token"], job["id"], unit_cost=None)

    assert material["unit_cost"] is None


@pytest.mark.asyncio
async def test_listing_materials_returns_them_in_order(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    first = await _add_material(client, owner["access_token"], job["id"], name="First")
    second = await _add_material(client, owner["access_token"], job["id"], name="Second")

    response = await client.get(f"/api/v1/jobs/{job['id']}/materials", headers=headers)

    assert response.status_code == 200
    ids = [m["id"] for m in response.json()]
    assert ids == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_editing_and_removing_a_material_updates_it_and_does_not_corrupt_the_timeline(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    material = await _add_material(client, owner["access_token"], job["id"], name="Typo'd Name")

    patch_response = await client.patch(
        f"/api/v1/jobs/{job['id']}/materials/{material['id']}",
        json={"name": "Corrected Name", "quantity": "3"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Corrected Name"
    assert float(patch_response.json()["quantity"]) == 3

    delete_response = await client.delete(
        f"/api/v1/jobs/{job['id']}/materials/{material['id']}", headers=headers
    )
    assert delete_response.status_code == 204

    list_response = await client.get(f"/api/v1/jobs/{job['id']}/materials", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json() == []

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    event_types = [e["event_type"] for e in timeline.json()]
    assert event_types == ["material_added", "material_edited", "material_removed"]
    # Chronological order preserved.
    created_ats = [e["created_at"] for e in timeline.json()]
    assert created_ats == sorted(created_ats)


@pytest.mark.asyncio
async def test_updating_or_removing_a_nonexistent_material_is_404(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    fake_id = str(uuid.uuid4())
    assert (
        await client.patch(
            f"/api/v1/jobs/{job['id']}/materials/{fake_id}", json={"name": "Nope"}, headers=headers
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/jobs/{job['id']}/materials/{fake_id}", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_technician_can_manage_materials_on_their_own_assigned_job(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    tech_token = technician["access_token"]

    material = await _add_material(client, tech_token, job["id"])
    patch_response = await client.patch(
        f"/api/v1/jobs/{job['id']}/materials/{material['id']}",
        json={"quantity": "5"},
        headers=_auth_headers(tech_token),
    )
    assert patch_response.status_code == 200

    delete_response = await client.delete(
        f"/api/v1/jobs/{job['id']}/materials/{material['id']}", headers=_auth_headers(tech_token)
    )
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_technician_gets_403_on_a_job_not_assigned_to_them(client):
    owner = await _register_org(client)
    technician_a = await _create_member(client, owner["access_token"], role="technician")
    technician_b = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician_b["id"])
    material = await _add_material(client, owner["access_token"], job["id"])

    headers_a = _auth_headers(technician_a["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{job['id']}/materials", json={"name": "X", "quantity": "1"}, headers=headers_a
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/jobs/{job['id']}/materials", headers=headers_a)).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/jobs/{job['id']}/materials/{material['id']}", json={"name": "X"}, headers=headers_a
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/v1/jobs/{job['id']}/materials/{material['id']}", headers=headers_a)
    ).status_code == 403


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404_not_403(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(client, org_a_owner["access_token"], customer_id=org_a_customer["id"])
    material = await _add_material(client, org_a_owner["access_token"], org_a_job["id"])

    org_b_owner = await _register_org(client)
    headers_b = _auth_headers(org_b_owner["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/materials", json={"name": "X", "quantity": "1"}, headers=headers_b
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/jobs/{org_a_job['id']}/materials", headers=headers_b)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/jobs/{org_a_job['id']}/materials/{material['id']}",
            json={"name": "X"},
            headers=headers_b,
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/jobs/{org_a_job['id']}/materials/{material['id']}", headers=headers_b)
    ).status_code == 404


@pytest.mark.asyncio
async def test_dispatcher_can_manage_materials_on_any_job(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    material = await _add_material(client, dispatcher["access_token"], job["id"])
    assert material["name"] == "Refrigerant R410A"
