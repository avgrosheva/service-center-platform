"""
Tests for Milestone 10's photo endpoints: presigned upload URL generation,
metadata confirmation, and listing.

Same pattern as test_jobs.py — real ASGI app, real database, no dependency
overrides. Presigned URL generation is pure local signing (boto3 doesn't
make a network call to compute it), so these tests don't require MinIO to
actually be reachable — they assert the URL's structure and expiry, not
that an upload against it would succeed. A real end-to-end upload is a
frontend/manual-smoke-test concern, not something the backend test suite
proves per the roadmap's own testing checklist.
"""

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.s3_client import PRESIGNED_URL_EXPIRY_SECONDS


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


async def _get_upload_url(
    client: AsyncClient, token: str, job_id: str, *, content_type: str = "image/jpeg", expected_status: int = 200
) -> dict:
    response = await client.post(
        f"/api/v1/jobs/{job_id}/photos/upload-url",
        json={"content_type": content_type},
        headers=_auth_headers(token),
    )
    assert response.status_code == expected_status, response.text
    return response.json()


async def _create_photo(
    client: AsyncClient, token: str, job_id: str, *, s3_key: str, tag: str | None = None, expected_status: int = 201
) -> dict:
    payload = {"s3_key": s3_key}
    if tag is not None:
        payload["tag"] = tag
    response = await client.post(
        f"/api/v1/jobs/{job_id}/photos", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == expected_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_upload_url_generation_succeeds_and_is_time_limited(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    body = await _get_upload_url(client, owner["access_token"], job["id"])

    assert body["upload_url"].startswith("http")
    assert body["s3_key"].startswith(f"{owner['organization_id']}/jobs/{job['id']}/photos/")
    assert body["s3_key"].endswith(".jpg")

    query = parse_qs(urlparse(body["upload_url"]).query)
    assert query["X-Amz-Expires"] == [str(PRESIGNED_URL_EXPIRY_SECONDS)]


@pytest.mark.asyncio
async def test_upload_url_rejects_an_unsupported_content_type(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/photos/upload-url",
        json={"content_type": "application/pdf"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_confirming_upload_persists_metadata_and_writes_timeline_entry(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    upload = await _get_upload_url(client, owner["access_token"], job["id"])

    photo = await _create_photo(
        client, owner["access_token"], job["id"], s3_key=upload["s3_key"], tag="before"
    )

    assert photo["job_id"] == job["id"]
    assert photo["s3_key"] == upload["s3_key"]
    assert photo["tag"] == "before"
    assert photo["uploaded_by_id"] == owner["user_id"]

    timeline = await client.get(f"/api/v1/jobs/{job['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    entries = timeline.json()
    assert any(e["event_type"] == "photo_added" for e in entries)


@pytest.mark.asyncio
async def test_confirming_upload_returns_a_time_limited_view_url(client):
    # Added alongside the frontend's Milestone F10 — PhotoRead.view_url is
    # a presigned GET, not a persisted column, so this asserts it's
    # actually generated (not just present-but-empty) and expires the same
    # way the upload URL does.
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    upload = await _get_upload_url(client, owner["access_token"], job["id"])

    photo = await _create_photo(client, owner["access_token"], job["id"], s3_key=upload["s3_key"])

    assert photo["view_url"].startswith("http")
    query = parse_qs(urlparse(photo["view_url"]).query)
    assert query["X-Amz-Expires"] == [str(PRESIGNED_URL_EXPIRY_SECONDS)]


@pytest.mark.asyncio
async def test_invalid_tag_is_rejected(client):
    owner = await _register_org(client)
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    response = await client.post(
        f"/api/v1/jobs/{job['id']}/photos",
        json={"s3_key": "some/key.jpg", "tag": "not-a-real-tag"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_listing_photos_returns_them_in_upload_order(client):
    owner = await _register_org(client)
    headers = _auth_headers(owner["access_token"])
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    first = await _create_photo(client, owner["access_token"], job["id"], s3_key="a.jpg", tag="before")
    second = await _create_photo(client, owner["access_token"], job["id"], s3_key="b.jpg", tag="after")

    response = await client.get(f"/api/v1/jobs/{job['id']}/photos", headers=headers)

    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert ids == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_technician_can_manage_photos_on_their_own_assigned_job(client):
    owner = await _register_org(client)
    technician = await _create_member(client, owner["access_token"], role="technician")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])
    await _assign(client, owner["access_token"], job["id"], technician["id"])
    tech_token = technician["access_token"]

    upload = await _get_upload_url(client, tech_token, job["id"])
    photo = await _create_photo(client, tech_token, job["id"], s3_key=upload["s3_key"])
    assert photo["uploaded_by_id"] == technician["id"]

    list_response = await client.get(f"/api/v1/jobs/{job['id']}/photos", headers=_auth_headers(tech_token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


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
            f"/api/v1/jobs/{job['id']}/photos/upload-url",
            json={"content_type": "image/jpeg"},
            headers=headers_a,
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/jobs/{job['id']}/photos", json={"s3_key": "x.jpg"}, headers=headers_a
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/jobs/{job['id']}/photos", headers=headers_a)).status_code == 403


@pytest.mark.asyncio
async def test_cross_org_job_id_is_404_not_403(client):
    org_a_owner = await _register_org(client)
    org_a_customer = await _create_customer(client, org_a_owner["access_token"])
    org_a_job = await _create_job(client, org_a_owner["access_token"], customer_id=org_a_customer["id"])

    org_b_owner = await _register_org(client)
    headers_b = _auth_headers(org_b_owner["access_token"])

    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/photos/upload-url",
            json={"content_type": "image/jpeg"},
            headers=headers_b,
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/jobs/{org_a_job['id']}/photos", json={"s3_key": "x.jpg"}, headers=headers_b
        )
    ).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{org_a_job['id']}/photos", headers=headers_b)).status_code == 404


@pytest.mark.asyncio
async def test_dispatcher_can_manage_photos_on_any_job(client):
    owner = await _register_org(client)
    dispatcher = await _create_member(client, owner["access_token"], role="dispatcher")
    customer = await _create_customer(client, owner["access_token"])
    job = await _create_job(client, owner["access_token"], customer_id=customer["id"])

    upload = await _get_upload_url(client, dispatcher["access_token"], job["id"])
    photo = await _create_photo(client, dispatcher["access_token"], job["id"], s3_key=upload["s3_key"])

    assert photo["uploaded_by_id"] == dispatcher["id"]
