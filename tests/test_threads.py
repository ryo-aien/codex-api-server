from __future__ import annotations

import pytest

from tests.conftest import create_client_with_key


@pytest.mark.asyncio
async def test_create_thread_success(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "investigate this repo"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["repository"] == "project-a"
    assert body["status"] == "completed"
    assert body["thread_id"].startswith("thr_")


@pytest.mark.asyncio
async def test_create_thread_unknown_repository_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "does-not-exist", "prompt": "investigate"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "repository_not_found"


@pytest.mark.asyncio
async def test_create_thread_path_traversal_rejected(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "../etc", "prompt": "investigate"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_empty_prompt_rejected(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_thread_prompt_too_long_rejected(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    huge_prompt = "a" * (test_settings.max_prompt_chars + 1)
    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": huge_prompt},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_message_does_not_accept_repository_override(app_client, repo, test_settings):
    """POST /v1/threads/{id}/messages resolves repository from thread metadata only."""
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    created = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "investigate"},
    )
    thread_id = created.json()["thread_id"]

    # The schema for this endpoint has no "repository" field at all, so even
    # if a client sends one it is silently ignored (extra fields dropped).
    response = await http_client.post(
        f"/v1/threads/{thread_id}/messages",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "continue", "repository": "some-other-repo"},
    )
    assert response.status_code == 200
    assert response.json()["repository"] == "project-a"


@pytest.mark.asyncio
async def test_list_threads_returns_only_own_threads(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"repository": "project-a", "prompt": "alice thread 1"},
    )
    await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"repository": "project-a", "prompt": "alice thread 2"},
    )
    await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"repository": "project-a", "prompt": "bob thread 1"},
    )

    alice_list = await http_client.get(
        "/v1/threads", headers={"Authorization": f"Bearer {alice_key}"}
    )
    bob_list = await http_client.get(
        "/v1/threads", headers={"Authorization": f"Bearer {bob_key}"}
    )

    assert alice_list.status_code == 200
    assert bob_list.status_code == 200
    assert len(alice_list.json()["threads"]) == 2
    assert len(bob_list.json()["threads"]) == 1


@pytest.mark.asyncio
async def test_archive_thread(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    created = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "investigate"},
    )
    thread_id = created.json()["thread_id"]

    response = await http_client.delete(
        f"/v1/threads/{thread_id}", headers={"Authorization": f"Bearer {raw_key}"}
    )
    assert response.status_code == 200
    assert response.json()["archived"] is True

    thread = await repo.get_thread(thread_id)
    assert thread.archived is True


@pytest.mark.asyncio
async def test_resume_nonexistent_thread_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads/thr_does_not_exist/messages",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "hello"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_times_out(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    # test_settings.codex_request_timeout == 5; make the fake Codex service
    # sleep past that so the request-level timeout kicks in.
    test_settings.codex_request_timeout = 0
    fake_codex_service.sleep_seconds = 0.2

    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "this will time out"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"
