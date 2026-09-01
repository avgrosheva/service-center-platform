"""
Tests for Milestone 5's authorization (require_role) and tenant-scoped
/users endpoints.

Same pattern as test_auth.py — real ASGI app, real database, no dependency
overrides — since the whole point is proving the actual role gate and
organization_id scoping work end to end.

test_cross_org_isolation_on_every_users_route below is written as the
reference pattern for cross-org isolation testing: every future module
that follows Milestone 5's tenant-scoping convention should repeat this
shape (own org's list never contains the other org's rows; every id-taking
route returns 404 — not 403, not a leaked 200 — for a cross-org id; and the
other org is provably unaffected afterwards).
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
    """Registers a brand-new organization + owner, returns creds and identity."""
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

    return {
        "access_token": access_token,
        "organization_id": profile["organization_id"],
        "user_id": profile["id"],
        "email": payload["email"],
        "password": password,
    }


async def _create_user(
    client: AsyncClient, owner_token: str, *, role: str, password: str = "member-password-1"
) -> dict:
    """Creates a user of the given role in the owner's org, returns creds and identity."""
    email = _unique_email()
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": f"Test {role.title()}", "role": role, "password": password},
        headers=_auth_headers(owner_token),
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text

    return {"id": user_id, "email": email, "password": password, "access_token": login.json()["access_token"]}


@pytest.mark.asyncio
async def test_technician_gets_403_on_every_users_route(client):
    owner = await _register_org(client)
    technician = await _create_user(client, owner["access_token"], role="technician")
    headers = _auth_headers(technician["access_token"])

    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/users/{owner['user_id']}", headers=headers)).status_code == 403
    assert (
        await client.post(
            "/api/v1/users",
            json={"email": _unique_email(), "full_name": "Nope", "role": "technician", "password": "x1234567"},
            headers=headers,
        )
    ).status_code == 403
    assert (
        await client.patch(f"/api/v1/users/{owner['user_id']}", json={"is_active": False}, headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/users/{owner['user_id']}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_dispatcher_can_list_and_view_but_forbidden_from_create_edit_delete(client):
    owner = await _register_org(client)
    dispatcher = await _create_user(client, owner["access_token"], role="dispatcher")
    headers = _auth_headers(dispatcher["access_token"])

    list_response = await client.get("/api/v1/users", headers=headers)
    assert list_response.status_code == 200
    emails = {u["email"] for u in list_response.json()}
    assert {owner["email"], dispatcher["email"]} <= emails

    detail_response = await client.get(f"/api/v1/users/{owner['user_id']}", headers=headers)
    assert detail_response.status_code == 200

    assert (
        await client.post(
            "/api/v1/users",
            json={"email": _unique_email(), "full_name": "Nope", "role": "technician", "password": "x1234567"},
            headers=headers,
        )
    ).status_code == 403
    assert (
        await client.patch(f"/api/v1/users/{owner['user_id']}", json={"is_active": False}, headers=headers)
    ).status_code == 403
    assert (await client.delete(f"/api/v1/users/{owner['user_id']}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_owner_can_perform_full_crud(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    create_response = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "full_name": "New Tech", "role": "technician", "password": "x1234567"},
        headers=headers,
    )
    assert create_response.status_code == 201
    new_user_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/users", headers=headers)
    assert any(u["id"] == new_user_id for u in list_response.json())

    detail_response = await client.get(f"/api/v1/users/{new_user_id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["role"] == "technician"

    patch_response = await client.patch(
        f"/api/v1/users/{new_user_id}", json={"role": "dispatcher"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["role"] == "dispatcher"

    delete_response = await client.delete(f"/api/v1/users/{new_user_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_cross_org_isolation_on_every_users_route(client):
    org_a_owner = await _register_org(client)
    org_b_owner = await _register_org(client)
    org_b_technician = await _create_user(client, org_b_owner["access_token"], role="technician")

    headers_a = _auth_headers(org_a_owner["access_token"])

    # Org A's own list never contains anyone from Org B.
    list_response = await client.get("/api/v1/users", headers=headers_a)
    assert list_response.status_code == 200
    org_a_visible_ids = {u["id"] for u in list_response.json()}
    assert org_b_owner["user_id"] not in org_a_visible_ids
    assert org_b_technician["id"] not in org_a_visible_ids

    # Org A's owner can't read, patch, or delete anyone in Org B — a
    # cross-org id must come back as 404, indistinguishable from an id
    # that was never issued at all (never 403, and never a leaked 200).
    for target_id in (org_b_owner["user_id"], org_b_technician["id"]):
        assert (await client.get(f"/api/v1/users/{target_id}", headers=headers_a)).status_code == 404
        assert (
            await client.patch(f"/api/v1/users/{target_id}", json={"is_active": False}, headers=headers_a)
        ).status_code == 404
        assert (await client.delete(f"/api/v1/users/{target_id}", headers=headers_a)).status_code == 404

    # Org B is provably unaffected by Org A's failed cross-org attempts —
    # its technician is still active and visible to its own owner.
    headers_b = _auth_headers(org_b_owner["access_token"])
    still_active = await client.get(f"/api/v1/users/{org_b_technician['id']}", headers=headers_b)
    assert still_active.status_code == 200
    assert still_active.json()["is_active"] is True


@pytest.mark.asyncio
async def test_owner_cannot_change_own_role(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    response = await client.patch(
        f"/api/v1/users/{owner['user_id']}", json={"role": "dispatcher"}, headers=headers
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_deactivating_the_sole_owner_is_rejected_via_delete(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    response = await client.delete(f"/api/v1/users/{owner['user_id']}", headers=headers)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_deactivating_the_sole_owner_is_rejected_via_patch(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])

    response = await client.patch(
        f"/api/v1/users/{owner['user_id']}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_deactivating_an_owner_succeeds_once_another_active_owner_exists(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    second_member = await _create_user(client, owner["access_token"], role="dispatcher")

    promote_response = await client.patch(
        f"/api/v1/users/{second_member['id']}", json={"role": "owner"}, headers=headers
    )
    assert promote_response.status_code == 200

    delete_response = await client.delete(f"/api/v1/users/{owner['user_id']}", headers=headers)

    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False
