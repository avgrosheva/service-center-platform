"""
Tests for Milestone 4's authentication endpoints and get_current_user.

Runs against the real (already-migrated) database via the real ASGI app,
same pattern as test_health.py (httpx.AsyncClient + ASGITransport) — no
dependency overrides for get_db, since these tests want to exercise the
actual register -> login -> refresh -> me round trip end to end.

Each test uses a fresh, uuid-suffixed email/org name so tests don't collide
with each other or with leftover data from previous runs.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.core.security import create_access_token
from app.database import AsyncSessionLocal
from app.main import app
from app.models.user import User, UserRole


def _unique_email() -> str:
    # email-validator (used by Pydantic's EmailStr) rejects the .test TLD as
    # a reserved special-use domain, unlike the .test emails used freely in
    # test_models.py — those go straight into the ORM and never pass
    # through EmailStr validation. example.com isn't on that reserved list.
    return f"user-{uuid.uuid4().hex}@example.com"


async def _register(client: AsyncClient, *, email: str | None = None, password: str = "correct-horse-1"):
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Ada Owner",
        "email": email or _unique_email(),
        "password": password,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    return response, payload


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_register_creates_organization_and_owner_with_usable_tokens(client):
    response, payload = await _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["email"] == payload["email"]
    assert me_body["full_name"] == payload["full_name"]
    assert me_body["role"] == "owner"


@pytest.mark.asyncio
async def test_login_with_correct_credentials_succeeds(client):
    _, payload = await _register(client, password="correct-horse-1")

    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client):
    _, payload = await _register(client, password="correct-horse-1")

    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": "totally-wrong-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_inactive_user(client):
    _, payload = await _register(client, password="correct-horse-1")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == payload["email"]))
        user = result.scalar_one()
        user.is_active = False
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_access_token_rejected_by_get_current_user(client):
    register_response, _ = await _register(client)
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {register_response.json()['access_token']}"},
    )
    profile = me_response.json()

    settings = get_settings()
    expired_settings = settings.model_copy(update={"jwt_access_token_expire_minutes": -5})
    expired_token = create_access_token(
        user_id=uuid.UUID(profile["id"]),
        organization_id=uuid.UUID(profile["organization_id"]),
        role=UserRole(profile["role"]),
        settings=expired_settings,
    )

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_and_malformed_tokens(client):
    no_token_response = await client.get("/api/v1/auth/me")
    assert no_token_response.status_code == 401

    bad_token_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert bad_token_response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_issues_a_new_working_access_token(client):
    register_response, payload = await _register(client)
    refresh_token = register_response.json()["refresh_token"]

    refresh_response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == payload["email"]


@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token_used_in_place_of_a_refresh_token(client):
    register_response, _ = await _register(client)
    access_token = register_response.json()["access_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_same_email_allowed_across_different_organizations_and_login_disambiguates(client):
    email = _unique_email()

    response_a, _ = await _register(client, email=email, password="org-a-password-1")
    response_b, _ = await _register(client, email=email, password="org-b-password-1")
    assert response_a.status_code == 201
    assert response_b.status_code == 201

    me_a = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response_a.json()['access_token']}"},
    )
    me_b = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response_b.json()['access_token']}"},
    )
    assert me_a.json()["organization_id"] != me_b.json()["organization_id"]

    login_a = await client.post("/api/v1/auth/login", json={"email": email, "password": "org-a-password-1"})
    login_b = await client.post("/api/v1/auth/login", json={"email": email, "password": "org-b-password-1"})
    assert login_a.status_code == 200
    assert login_b.status_code == 200

    profile_a = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login_a.json()['access_token']}"}
    )
    profile_b = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login_b.json()['access_token']}"}
    )
    assert profile_a.json()["organization_id"] == me_a.json()["organization_id"]
    assert profile_b.json()["organization_id"] == me_b.json()["organization_id"]


@pytest.mark.asyncio
async def test_same_email_and_password_across_orgs_deterministically_logs_into_the_first_registered(client):
    # If two different organizations happen to register a user with the
    # exact same email *and* the exact same password, login can't tell them
    # apart by credentials alone. auth_service.login breaks the tie by
    # (created_at, id) — this test locks that in as the earliest-registered
    # account, checked repeatedly since an unordered query could otherwise
    # "happen" to return a stable-looking order by luck.
    email = _unique_email()
    shared_password = "identical-password-1"

    response_first, _ = await _register(client, email=email, password=shared_password)
    response_second, _ = await _register(client, email=email, password=shared_password)
    assert response_first.status_code == 201
    assert response_second.status_code == 201

    first_profile = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response_first.json()['access_token']}"},
    )
    expected_org_id = first_profile.json()["organization_id"]

    for _ in range(5):
        login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": shared_password})
        assert login_response.status_code == 200

        profile = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
        )
        assert profile.json()["organization_id"] == expected_org_id
