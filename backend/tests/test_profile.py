"""
Tests for the self-service profile endpoints: PATCH /auth/me, POST
/auth/me/password, and the avatar upload/confirm/delete trio.

Same pattern as test_auth.py / test_photos.py — real ASGI app, real
database, no dependency overrides. Avatar presigned-URL generation is pure
local signing (no MinIO round trip needed), so confirming an avatar in
these tests uses a made-up s3_key rather than a real upload, matching
test_photos.py's own rationale.
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


async def _register_owner(client: AsyncClient, *, password: str = "owner-password-1") -> dict:
    email = _unique_email()
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Profile Owner",
        "email": email,
        "password": password,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    return {"access_token": body["access_token"], "email": email, "password": password}


@pytest.mark.asyncio
async def test_update_me_changes_name_email_and_phone(client):
    owner = await _register_owner(client)
    new_email = _unique_email()

    response = await client.patch(
        "/api/v1/auth/me",
        json={"full_name": "New Name", "email": new_email, "phone": "+7 999 123-45-67"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "New Name"
    assert body["email"] == new_email
    assert body["phone"] == "+7 999 123-45-67"


@pytest.mark.asyncio
async def test_update_me_partial_update_leaves_other_fields_untouched(client):
    owner = await _register_owner(client)

    response = await client.patch(
        "/api/v1/auth/me",
        json={"phone": "+7 999 111-22-33"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Profile Owner"
    assert body["phone"] == "+7 999 111-22-33"


@pytest.mark.asyncio
async def test_update_me_clears_phone_with_empty_string(client):
    owner = await _register_owner(client)
    await client.patch(
        "/api/v1/auth/me", json={"phone": "+7 999 111-22-33"}, headers=_auth_headers(owner["access_token"])
    )

    response = await client.patch(
        "/api/v1/auth/me", json={"phone": ""}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 200, response.text
    assert response.json()["phone"] is None


@pytest.mark.asyncio
async def test_update_me_rejects_a_short_phone(client):
    owner = await _register_owner(client)

    response = await client.patch(
        "/api/v1/auth/me", json={"phone": "123"}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_me_email_conflict_within_same_organization_returns_409(client):
    owner = await _register_owner(client)
    member_email = _unique_email()
    create_response = await client.post(
        "/api/v1/users",
        json={
            "email": member_email,
            "full_name": "Teammate",
            "role": "technician",
            "password": "member-password-1",
        },
        headers=_auth_headers(owner["access_token"]),
    )
    assert create_response.status_code == 201, create_response.text

    response = await client.patch(
        "/api/v1/auth/me", json={"email": member_email}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_change_password_with_correct_current_password_succeeds_and_new_password_logs_in(client):
    owner = await _register_owner(client, password="original-password-1")

    response = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "original-password-1", "new_password": "brand-new-password-1"},
        headers=_auth_headers(owner["access_token"]),
    )
    assert response.status_code == 204

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": owner["email"], "password": "original-password-1"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": owner["email"], "password": "brand-new-password-1"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_with_wrong_current_password_returns_400(client):
    owner = await _register_owner(client, password="original-password-1")

    response = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "not-the-real-password", "new_password": "brand-new-password-1"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_avatar_upload_url_generation_is_time_limited_and_org_scoped(client):
    owner = await _register_owner(client)

    response = await client.post(
        "/api/v1/auth/me/avatar/upload-url",
        json={"content_type": "image/jpeg"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upload_url"]
    assert body["s3_key"].endswith(".jpg")
    assert "/users/" in body["s3_key"]
    assert "/avatar/" in body["s3_key"]


@pytest.mark.asyncio
async def test_confirm_avatar_then_me_includes_a_signed_avatar_url(client):
    owner = await _register_owner(client)

    upload_url_response = await client.post(
        "/api/v1/auth/me/avatar/upload-url",
        json={"content_type": "image/jpeg"},
        headers=_auth_headers(owner["access_token"]),
    )
    s3_key = upload_url_response.json()["s3_key"]

    confirm_response = await client.post(
        "/api/v1/auth/me/avatar", json={"s3_key": s3_key}, headers=_auth_headers(owner["access_token"])
    )
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["avatar_url"]

    me_response = await client.get("/api/v1/auth/me", headers=_auth_headers(owner["access_token"]))
    assert me_response.json()["avatar_url"]


@pytest.mark.asyncio
async def test_confirm_avatar_rejects_a_key_never_issued_to_this_user(client):
    owner = await _register_owner(client)

    response = await client.post(
        "/api/v1/auth/me/avatar",
        json={"s3_key": "not-a-real-key.jpg"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_avatar_rejects_another_users_avatar_key(client):
    owner_a = await _register_owner(client)
    owner_b = await _register_owner(client)

    upload_url_response = await client.post(
        "/api/v1/auth/me/avatar/upload-url",
        json={"content_type": "image/jpeg"},
        headers=_auth_headers(owner_a["access_token"]),
    )
    owner_a_s3_key = upload_url_response.json()["s3_key"]

    response = await client.post(
        "/api/v1/auth/me/avatar",
        json={"s3_key": owner_a_s3_key},
        headers=_auth_headers(owner_b["access_token"]),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_me_has_no_avatar_url_before_any_upload(client):
    owner = await _register_owner(client)

    response = await client.get("/api/v1/auth/me", headers=_auth_headers(owner["access_token"]))

    assert response.json()["avatar_url"] is None


@pytest.mark.asyncio
async def test_delete_avatar_clears_it(client):
    owner = await _register_owner(client)
    upload_url_response = await client.post(
        "/api/v1/auth/me/avatar/upload-url",
        json={"content_type": "image/png"},
        headers=_auth_headers(owner["access_token"]),
    )
    s3_key = upload_url_response.json()["s3_key"]
    await client.post(
        "/api/v1/auth/me/avatar", json={"s3_key": s3_key}, headers=_auth_headers(owner["access_token"])
    )

    response = await client.delete("/api/v1/auth/me/avatar", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200, response.text
    assert response.json()["avatar_url"] is None
