"""
Tests for Milestone 18's "AI_ENABLED gates route registration, not just
access" requirement.

With AI_ENABLED=false (the default — app.main.app, the process's real
singleton, is built with it off), every /ai/* path must 404, and it must
404 for *any* caller, authenticated or not — proving the routes simply
don't exist in FastAPI's routing table, rather than existing and being
turned away by a role check (which would be 401/403). With AI_ENABLED=
true, the same paths must exist (not 404) — checked here via a 422
(validation error on a deliberately empty body) or a real 201/200,
anything other than 404, since the point is route *existence*, not this
test re-proving the full request/response contract already covered by
test_ai_tasks.py.

Building two separate FastAPI app instances via app.main.create_app() —
rather than toggling a module-level singleton — is what makes both states
testable in the same process: app.main.app is built once, at import time,
from whatever AI_ENABLED actually is in the environment (false, per
.env), so proving the *true* branch also works requires constructing a
second app with a different Settings object, not just asserting against
the one singleton.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app as disabled_app
from app.main import create_app


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def disabled_client():
    # app.main.app is the real process singleton, built from the actual
    # .env — AI_ENABLED defaults to false there, matching the production
    # default this test is meant to prove.
    transport = ASGITransport(app=disabled_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def enabled_client():
    enabled_settings = get_settings().model_copy(update={"ai_enabled": True})
    enabled_app = create_app(enabled_settings)
    transport = ASGITransport(app=enabled_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register_org(client: AsyncClient) -> dict:
    payload = {
        "organization_name": f"Org {uuid.uuid4().hex[:8]}",
        "full_name": "Org Owner",
        "email": _unique_email(),
        "password": "owner-password-1",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return {"access_token": response.json()["access_token"]}


@pytest.mark.asyncio
async def test_ai_routes_404_when_disabled_even_with_no_auth(disabled_client):
    # No Authorization header at all — if this came back 401 instead of
    # 404, that would itself prove the route exists (a 401 requires a
    # route to exist behind which to check credentials).
    assert (await disabled_client.post("/api/v1/ai/voice-note", json={"transcript": "x"})).status_code == 404
    assert (
        await disabled_client.post(f"/api/v1/ai/jobs/{uuid.uuid4()}/summary")
    ).status_code == 404
    assert (
        await disabled_client.post(f"/api/v1/ai/jobs/{uuid.uuid4()}/suggest-additional-work")
    ).status_code == 404
    assert (await disabled_client.post("/api/v1/ai/query", json={"query": "x"})).status_code == 404
    assert (await disabled_client.get(f"/api/v1/ai/tasks/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_ai_routes_404_when_disabled_even_with_valid_auth(disabled_client):
    # Same as above, but with a real, valid owner token — ruling out "it's
    # 404 only because auth failed first." A route that existed and was
    # merely role-gated would return 200/201/422 here, never 404.
    owner = await _register_org(disabled_client)
    headers = _auth_headers(owner["access_token"])

    assert (
        await disabled_client.post("/api/v1/ai/voice-note", json={"transcript": "x"}, headers=headers)
    ).status_code == 404
    assert (await disabled_client.post("/api/v1/ai/query", json={"query": "x"}, headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_rest_of_the_app_is_unaffected_by_ai_being_disabled(disabled_client):
    # "the app is fully functional with every AI feature disabled" —
    # proven concretely: register + login still work end to end on the
    # exact app instance where /ai/* 404s.
    owner = await _register_org(disabled_client)
    me = await disabled_client.get("/api/v1/auth/me", headers=_auth_headers(owner["access_token"]))
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_ai_routes_exist_when_enabled(enabled_client):
    owner = await _register_org(enabled_client)
    headers = _auth_headers(owner["access_token"])

    # A route that doesn't exist is always 404 regardless of body content;
    # a deliberately empty body would 422 (unprocessable — a validation
    # failure on a route that exists) rather than 404 on a route that
    # exists, proving existence without duplicating test_ai_tasks.py's
    # full success-path coverage.
    voice_note = await enabled_client.post("/api/v1/ai/voice-note", json={}, headers=headers)
    assert voice_note.status_code == 422

    query = await enabled_client.post("/api/v1/ai/query", json={}, headers=headers)
    assert query.status_code == 422


@pytest.mark.asyncio
async def test_ai_task_not_found_is_distinguishable_from_route_not_found(enabled_client, disabled_client):
    # The ambiguity flagged above (a 404 for "job not found" on an
    # existing route looks identical, over the wire, to "route doesn't
    # exist") is resolved by this pair: the same GET /ai/tasks/{id} path
    # 404s on the *disabled* app (route doesn't exist) and 404s on the
    # *enabled* app for a real, nonexistent task id (route exists, row
    # doesn't) — both 404, but for different reasons, which is why route
    # existence must always be checked via the disabled/enabled app split
    # above, never inferred from a single status code in isolation.
    owner = await _register_org(enabled_client)
    headers = _auth_headers(owner["access_token"])

    on_disabled_app = await disabled_client.get(f"/api/v1/ai/tasks/{uuid.uuid4()}")
    on_enabled_app = await enabled_client.get(f"/api/v1/ai/tasks/{uuid.uuid4()}", headers=headers)

    assert on_disabled_app.status_code == 404
    assert on_enabled_app.status_code == 404
    # Confirms the enabled app's route genuinely exists and ran real
    # logic: unauthenticated on the SAME enabled app 401s (a route that
    # exists demands credentials), whereas the disabled app 404s even
    # with valid credentials (see the test above) — different failure
    # reasons produce different status codes once auth is in play.
    unauthenticated_on_enabled = await enabled_client.get(f"/api/v1/ai/tasks/{uuid.uuid4()}")
    assert unauthenticated_on_enabled.status_code == 401
