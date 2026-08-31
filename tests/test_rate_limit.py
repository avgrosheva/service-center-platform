"""
Tests for Milestone 19's /auth/login rate limiting
(app.core.rate_limit.enforce_login_rate_limit).

conftest.py's `_reset_login_rate_limiter` autouse fixture clears the
in-memory counter before and after every test, so each test here starts
from a clean slate regardless of how many other tests in the suite also
call /auth/login.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register_org(client: AsyncClient, *, email: str, password: str) -> None:
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Org Owner",
        "email": email,
        "password": password,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_repeated_failed_logins_are_throttled_after_five_attempts(client):
    email = _unique_email()
    await _register_org(client, email=email, password="correct-password-1")

    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert response.status_code == 401

    sixth_response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert sixth_response.status_code == 429
    assert isinstance(sixth_response.json()["detail"], str)


@pytest.mark.asyncio
async def test_successful_logins_also_count_toward_the_limit(client):
    # Documented design decision: every attempt counts, not only failed
    # ones — the sixth login within the window is throttled even with
    # the correct password, matching how most real-world login limiters
    # behave (GitHub, AWS, etc. rate-limit by attempt count, not outcome).
    email = _unique_email()
    password = "correct-password-1"
    await _register_org(client, email=email, password=password)

    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200

    sixth_response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert sixth_response.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_is_scoped_by_client_not_by_the_email_being_attempted(client):
    # All requests through ASGITransport share the same fake client IP,
    # so this also proves the limiter keys on the caller (IP), not on
    # which email is in the request body: five failed attempts against
    # one email exhaust the limit for a completely different (and even
    # nonexistent) email from the "same" caller right after.
    email_a = _unique_email()
    await _register_org(client, email=email_a, password="correct-password-1")

    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json={"email": email_a, "password": "wrong"})
        assert response.status_code == 401

    unrelated_response = await client.post(
        "/api/v1/auth/login", json={"email": "someone-else-entirely@example.com", "password": "whatever"}
    )
    assert unrelated_response.status_code == 429


@pytest.mark.asyncio
async def test_register_is_not_rate_limited(client):
    # Scope check: only /login is gated per the roadmap's "login
    # especially" — repeated /register calls (each with a fresh unique
    # email, since duplicate registration isn't the thing being tested
    # here) must never 429.
    for _ in range(6):
        email = _unique_email()
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": f"Org {uuid.uuid4().hex[:8]}",
                "full_name": "Owner",
                "email": email,
                "password": "owner-password-1",
            },
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_refresh_is_not_rate_limited(client):
    email = _unique_email()
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Owner",
        "email": email,
        "password": "owner-password-1",
    }
    register_response = await client.post("/api/v1/auth/register", json=payload)
    refresh_token = register_response.json()["refresh_token"]

    for _ in range(6):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_user_well_under_the_limit_is_never_throttled(client):
    email = _unique_email()
    password = "correct-password-1"
    await _register_org(client, email=email, password=password)

    for _ in range(3):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
