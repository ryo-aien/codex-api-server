from __future__ import annotations

import pytest

from app.security.principals import AuthenticatedPrincipal


def test_principal_is_admin_property():
    admin = AuthenticatedPrincipal(
        client_id="admin", display_name="Admin", role="admin", key_id="cak_1"
    )
    user = AuthenticatedPrincipal(
        client_id="alice", display_name="Alice", role="user", key_id="cak_2"
    )
    assert admin.is_admin is True
    assert user.is_admin is False


@pytest.mark.asyncio
async def test_me_endpoint_never_returns_api_key(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    _client, raw_key, _key_id = await create_client_with_key(repo, test_settings, "alice")
    http_client, _app = app_client

    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 200
    body = response.json()
    serialized = str(body)
    assert raw_key not in serialized
    assert "cax_" not in serialized
