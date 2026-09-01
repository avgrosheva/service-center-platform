"""
Tests for Milestone 19's centralized exception handling
(app.core.exceptions.register_exception_handlers).

Three shapes are checked against each other to prove they're now
consistent: a deliberate HTTPException (already consistent before this
milestone, included here as the baseline), a Pydantic validation failure
(previously a list under `detail`), and a genuinely unhandled exception
(previously a bare-text, non-JSON 500). All three must return
`{"detail": "<string>"}` — same key, same value type — which is exactly
what "Error responses consistent in shape across all modules" means.
"""

import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import customer_service


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
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
async def test_deliberate_http_exception_returns_string_detail(client):
    # Baseline: this was already true before Milestone 19 — a 404 from a
    # router's own `raise HTTPException(..., detail=str(exc))`.
    owner = await _register_org(client)
    response = await client.get(f"/api/v1/customers/{uuid.uuid4()}", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_validation_error_returns_string_detail_not_a_list(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/customers", json={"full_name": "", "phone": "+79991234567"}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["detail"] != ""
    # The field that actually failed should be traceable in the message.
    assert "full_name" in body["detail"]


@pytest.mark.asyncio
async def test_validation_error_on_missing_required_field_is_still_a_string(client):
    owner = await _register_org(client)

    response = await client.post(
        "/api/v1/jobs", json={"reported_issue": "no customer_id given"}, headers=_auth_headers(owner["access_token"])
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_with_consistent_shape(monkeypatch, caplog):
    # A generic-Exception handler is registered on Starlette's
    # ServerErrorMiddleware (not ExceptionMiddleware) — Starlette sends
    # the handler's response to the real HTTP client but *also* re-raises
    # the original exception afterward, specifically so logging/debugging
    # tooling still sees it. httpx's ASGITransport defaults to re-raising
    # that into the calling test (`raise_app_exceptions=True`), which
    # would make this test fail with the injected RuntimeError instead of
    # inspecting the response my handler actually sent — so this test
    # alone needs its own client with that off, unlike every other test
    # in this suite, which wants exceptions to propagate immediately so
    # real bugs surface as loud test failures, not silent 500s.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated unexpected bug")

        monkeypatch.setattr(customer_service, "list_customers", _boom)

        owner = await _register_org(client)

        with caplog.at_level(logging.ERROR, logger="app.core.exceptions"):
            response = await client.get("/api/v1/customers", headers=_auth_headers(owner["access_token"]))

        assert response.status_code == 500
        # Same {"detail": "<string>"} shape as every other error — and
        # deliberately generic: no exception class name, no stack trace,
        # no hint of "RuntimeError" or "simulated unexpected bug" leaked
        # to the client, even though that's exactly what broke.
        assert response.json() == {"detail": "An unexpected error occurred"}

    # But it IS captured server-side, with the real exception detail —
    # "silently disappears" is exactly what this handler rules out.
    assert "Unhandled exception on GET /api/v1/customers" in caplog.text
    assert "simulated unexpected bug" in caplog.text
