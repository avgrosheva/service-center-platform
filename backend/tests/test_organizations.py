"""
Tests for GET /organizations/me — added post-Milestone-19 for the
frontend's Milestone F3 (see app/routers/organizations.py's docstring for
why: the frontend's user menu needs the caller's own organization name,
and no existing endpoint returned it).

Same pattern as the rest of the suite — real ASGI app, real database, no
dependency overrides. There's no cross-org isolation test in the usual
shape (a request for another organization's row, expecting 404) because
this endpoint has no organization_id parameter for a client to supply at
all — it always returns the caller's own organization, so the "leak
another tenant's data" failure mode this pattern normally guards against
doesn't have a way to occur here. What's tested instead: two different
organizations each get back their own (different) name, never each
other's.
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


async def _register_org(client: AsyncClient, *, organization_name: str) -> dict:
    payload = {
        "organization_name": organization_name,
        "full_name": "Org Owner",
        "email": _unique_email(),
        "password": "owner-password-1",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return {"access_token": response.json()["access_token"]}


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


@pytest.mark.asyncio
async def test_returns_the_callers_own_organization_name(client):
    org_name = f"Acme Repairs {uuid.uuid4().hex[:8]}"
    owner = await _register_org(client, organization_name=org_name)

    response = await client.get("/api/v1/organizations/me", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == org_name
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


@pytest.mark.asyncio
async def test_technician_and_dispatcher_can_also_read_their_own_organization(client):
    # No role restriction, unlike most of this API — every role's nav
    # shell shows the same user menu, so every role needs this.
    owner = await _register_org(client, organization_name=f"Org {uuid.uuid4().hex[:8]}")
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    technician = await _create_member(client, owner["access_token"], role="technician")

    for member in (dispatcher, technician):
        response = await client.get("/api/v1/organizations/me", headers=_auth_headers(member["access_token"]))
        assert response.status_code == 200

    dispatcher_body = (
        await client.get("/api/v1/organizations/me", headers=_auth_headers(dispatcher["access_token"]))
    ).json()
    technician_body = (
        await client.get("/api/v1/organizations/me", headers=_auth_headers(technician["access_token"]))
    ).json()
    assert dispatcher_body["name"] == technician_body["name"]


@pytest.mark.asyncio
async def test_each_organization_only_ever_sees_its_own_name(client):
    org_a_name = f"Org A {uuid.uuid4().hex[:8]}"
    org_b_name = f"Org B {uuid.uuid4().hex[:8]}"
    org_a_owner = await _register_org(client, organization_name=org_a_name)
    org_b_owner = await _register_org(client, organization_name=org_b_name)

    org_a_response = await client.get(
        "/api/v1/organizations/me", headers=_auth_headers(org_a_owner["access_token"])
    )
    org_b_response = await client.get(
        "/api/v1/organizations/me", headers=_auth_headers(org_b_owner["access_token"])
    )

    assert org_a_response.json()["name"] == org_a_name
    assert org_b_response.json()["name"] == org_b_name
    assert org_a_response.json()["id"] != org_b_response.json()["id"]


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client):
    response = await client.get("/api/v1/organizations/me")

    assert response.status_code == 401
