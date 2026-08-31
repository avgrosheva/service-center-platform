"""
Tests for the /health endpoint.

DB reachability is exercised via FastAPI's app.dependency_overrides for
get_settings (injecting a Settings instance directly) combined with
monkeypatching asyncpg.connect — this avoids needing a live Postgres
instance while still exercising the real code path in app.main.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import app


def _settings_override() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://fsp:dev_password_change_me@localhost:5432/field_service",
        jwt_secret="test-secret-do-not-use-in-production",
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_returns_200_when_database_reachable(monkeypatch):
    app.dependency_overrides[get_settings] = _settings_override

    class _FakeConnection:
        async def execute(self, query):
            return "SELECT 1"

        async def close(self):
            return None

    async def _fake_connect(dsn, timeout):
        return _FakeConnection()

    monkeypatch.setattr("app.main.asyncpg.connect", _fake_connect)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["environment"] == "development"


@pytest.mark.asyncio
async def test_health_returns_503_when_database_unreachable(monkeypatch):
    app.dependency_overrides[get_settings] = _settings_override

    async def _fake_connect_that_fails(dsn, timeout):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr("app.main.asyncpg.connect", _fake_connect_that_fails)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "database unreachable" in body["detail"]
