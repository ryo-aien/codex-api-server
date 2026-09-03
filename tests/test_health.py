from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_no_auth_required(app_client):
    client, _app = app_client
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ready"
    assert "codex" in body
    assert "authenticated" in body


@pytest.mark.asyncio
async def test_health_does_not_leak_secrets(app_client):
    client, _app = app_client
    response = await client.get("/health")
    body = response.json()
    serialized = str(body)
    assert "pepper" not in serialized.lower()
    assert "api_key" not in serialized.lower()
    assert "token" not in serialized.lower()
