from __future__ import annotations

import pytest

from tests.conftest import create_client_with_key


@pytest.mark.asyncio
async def test_chat_success_without_repository(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "こんにちは"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["response"] is not None


@pytest.mark.asyncio
async def test_chat_requires_auth(app_client):
    http_client, _app = app_client
    response = await http_client.post("/v1/chat", json={"prompt": "hi"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_empty_prompt_rejected(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_prompt_too_long_rejected(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    huge = "a" * (test_settings.max_prompt_chars + 1)
    response = await http_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": huge},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_chat_writes_audit_row(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")

    await http_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "some prompt body"},
    )

    rows = await repo.list_audit_logs(client_id="alice", limit=10)
    assert len(rows) >= 1
    row = rows[0]
    assert row["client_id"] == "alice"
    assert row["key_id"] == key_id
    assert row["action"] == "chat"
    assert row["prompt_chars"] == len("some prompt body")
    # The full prompt text must not be stored.
    conn = repo._db.raw
    audit_rows = conn.execute("SELECT * FROM audit_logs").fetchall()
    for r in audit_rows:
        serialized = " ".join(str(r[k]) for k in r.keys())
        assert "some prompt body" not in serialized


@pytest.mark.asyncio
async def test_chat_times_out(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    test_settings.codex_request_timeout = 0
    fake_codex_service.sleep_seconds = 0.2

    response = await http_client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "this will time out"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"


# -- history-backed conversations -------------------------------------------


@pytest.mark.asyncio
async def test_conversation_start_returns_id(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/chat/conversations",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "私の名前はryo"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["status"] == "completed"

    # ownership row is stored
    conv = await repo.get_conversation(body["conversation_id"])
    assert conv is not None
    assert conv.owner_client_id == "alice"


@pytest.mark.asyncio
async def test_conversation_continues_with_context(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    started = await http_client.post(
        "/v1/chat/conversations",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "turn one"},
    )
    conv_id = started.json()["conversation_id"]

    follow = await http_client.post(
        f"/v1/chat/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "turn two"},
    )
    assert follow.status_code == 200
    body = follow.json()
    assert body["conversation_id"] == conv_id
    # Fake echoes the turn count; 2 proves the prior turn was retained.
    assert "2 turns" in body["response"]


@pytest.mark.asyncio
async def test_conversation_other_user_cannot_continue(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    started = await http_client.post(
        "/v1/chat/conversations",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"prompt": "alice's conversation"},
    )
    conv_id = started.json()["conversation_id"]

    response = await http_client.post(
        f"/v1/chat/conversations/{conv_id}/messages",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "hijack"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


@pytest.mark.asyncio
async def test_continue_nonexistent_conversation_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/chat/conversations/thr_missing/messages",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "hello"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_conversations_only_own(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    for prompt in ["a1", "a2"]:
        await http_client.post(
            "/v1/chat/conversations",
            headers={"Authorization": f"Bearer {alice_key}"},
            json={"prompt": prompt},
        )
    await http_client.post(
        "/v1/chat/conversations",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "b1"},
    )

    alice_list = await http_client.get(
        "/v1/chat/conversations", headers={"Authorization": f"Bearer {alice_key}"}
    )
    bob_list = await http_client.get(
        "/v1/chat/conversations", headers={"Authorization": f"Bearer {bob_key}"}
    )
    assert len(alice_list.json()["conversations"]) == 2
    assert len(bob_list.json()["conversations"]) == 1
