from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.db import api_keys as api_keys_db
from app.db import clients as clients_db
from app.security.api_keys import (
    generate_key_id,
    generate_raw_api_key,
    hash_api_key,
    verify_api_key,
)


def test_generate_raw_api_key_format_and_entropy():
    key = generate_raw_api_key()
    assert key.startswith("cax_")
    # secrets.token_urlsafe(32) => 43 chars of base64url; plus the "cax_" prefix.
    assert len(key) >= 43 + 4


def test_generate_key_id_format():
    key_id = generate_key_id()
    assert key_id.startswith("cak_")


def test_hash_is_deterministic_and_verifiable():
    raw = generate_raw_api_key()
    pepper = "pepper-a"
    digest = hash_api_key(raw, pepper)
    assert verify_api_key(raw, pepper, digest)
    assert not verify_api_key("cax_wrong", pepper, digest)


def test_same_key_same_pepper_same_digest():
    raw = generate_raw_api_key()
    pepper = "pepper-a"
    assert hash_api_key(raw, pepper) == hash_api_key(raw, pepper)


def test_same_key_different_pepper_different_digest():
    raw = generate_raw_api_key()
    assert hash_api_key(raw, "pepper-a") != hash_api_key(raw, "pepper-b")


@pytest.mark.asyncio
async def test_raw_key_never_stored_in_db(repo):
    client = await repo.create_client("alice", "Alice")
    raw_key = generate_raw_api_key()
    key_id = generate_key_id()
    key_hash = hash_api_key(raw_key, "pepper")
    await repo.create_api_key(client.id, key_id, key_hash)

    conn: sqlite3.Connection = repo._db.raw  # inspect the raw DB directly
    rows = conn.execute("SELECT * FROM api_keys").fetchall()
    assert len(rows) == 1
    row = rows[0]
    # The raw key string must never appear verbatim anywhere in the row.
    for value in row.keys():
        assert raw_key not in str(row[value])
    assert row["key_hash"] == key_hash
    assert row["key_hash"] != raw_key


@pytest.mark.asyncio
async def test_valid_key_authenticates(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    client, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")
    http_client, _app = app_client

    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["client_id"] == "alice"
    assert body["key_id"] == key_id


@pytest.mark.asyncio
async def test_invalid_key_rejected(app_client):
    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": "Bearer cax_totally_made_up"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_authorization_header_rejected(app_client):
    http_client, _app = app_client
    response = await http_client.get("/v1/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_malformed_bearer_rejected(app_client):
    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": "Basic somebase64"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disabled_key_rejected(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    _client, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")
    await repo.set_api_key_enabled(key_id, False)

    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoked_key_rejected(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    _client, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")
    await repo.revoke_api_key(key_id)

    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_key_rejected(app_client, repo, test_settings):
    client = await repo.create_client("alice", "Alice")
    raw_key = generate_raw_api_key()
    key_id = generate_key_id()
    key_hash = hash_api_key(raw_key, test_settings.api_key_pepper)

    def _insert_expired(conn: sqlite3.Connection):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn.execute(
            """
            INSERT INTO api_keys (client_db_id, key_id, key_hash, enabled, created_at, expires_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (client.id, key_id, key_hash, past, past),
        )
        conn.commit()

    await repo._db.run(_insert_expired)

    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disabled_client_rejected(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    client, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")
    await repo.set_client_enabled("alice", False)

    http_client, _app = app_client
    response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_multiple_keys_same_client(repo, test_settings):
    client = await repo.create_client("alice", "Alice")

    raw1 = generate_raw_api_key()
    key_id1 = generate_key_id()
    await repo.create_api_key(client.id, key_id1, hash_api_key(raw1, test_settings.api_key_pepper))

    raw2 = generate_raw_api_key()
    key_id2 = generate_key_id()
    await repo.create_api_key(client.id, key_id2, hash_api_key(raw2, test_settings.api_key_pepper))

    keys = await repo.list_api_keys_by_client(client.id)
    assert len(keys) == 2
    assert {k.key_id for k in keys} == {key_id1, key_id2}


@pytest.mark.asyncio
async def test_key_rotation_old_key_stops_working(app_client, repo, test_settings):
    from tests.conftest import create_client_with_key

    client, old_raw, old_key_id = await create_client_with_key(repo, test_settings, "alice")

    new_raw = generate_raw_api_key()
    new_key_id = generate_key_id()
    await repo.create_api_key(
        client.id, new_key_id, hash_api_key(new_raw, test_settings.api_key_pepper)
    )
    await repo.revoke_api_key(old_key_id)

    http_client, _app = app_client

    old_response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {old_raw}"}
    )
    assert old_response.status_code == 401

    new_response = await http_client.get(
        "/v1/me", headers={"Authorization": f"Bearer {new_raw}"}
    )
    assert new_response.status_code == 200
