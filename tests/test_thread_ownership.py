from __future__ import annotations

import pytest

from tests.conftest import create_client_with_key


async def _create_thread(http_client, raw_key: str, repository: str, prompt: str) -> str:
    response = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": repository, "prompt": prompt},
    )
    assert response.status_code == 200
    return response.json()["thread_id"]


@pytest.mark.asyncio
async def test_owner_can_resume_own_thread(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, alice_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    thread_id = await _create_thread(http_client, alice_key, "project-a", "investigate")

    response = await http_client.post(
        f"/v1/threads/{thread_id}/messages",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"prompt": "continue please"},
    )
    assert response.status_code == 200
    assert response.json()["thread_id"] == thread_id


@pytest.mark.asyncio
async def test_other_user_cannot_resume_thread(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    thread_a = await _create_thread(http_client, alice_key, "project-a", "investigate")

    response = await http_client.post(
        f"/v1/threads/{thread_a}/messages",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "hijack attempt"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_archive_returns_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    thread_b = await _create_thread(http_client, bob_key, "project-a", "bob's work")

    response = await http_client.delete(
        f"/v1/threads/{thread_b}",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_stream_returns_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    thread_a = await _create_thread(http_client, alice_key, "project-a", "alice's work")

    response = await http_client.post(
        f"/v1/threads/{thread_a}/stream",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "steal this thread"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_interrupt_returns_404(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    thread_a = await _create_thread(http_client, alice_key, "project-a", "alice's work")

    response = await http_client.post(
        f"/v1/threads/{thread_a}/interrupt",
        headers={"Authorization": f"Bearer {bob_key}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_owner_boundaries_both_directions(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    thread_a = await _create_thread(http_client, alice_key, "project-a", "alice's work")
    thread_b = await _create_thread(http_client, bob_key, "project-a", "bob's work")

    ok_a = await http_client.post(
        f"/v1/threads/{thread_a}/messages",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"prompt": "continue"},
    )
    assert ok_a.status_code == 200

    ok_b = await http_client.post(
        f"/v1/threads/{thread_b}/messages",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "continue"},
    )
    assert ok_b.status_code == 200

    cross_1 = await http_client.post(
        f"/v1/threads/{thread_b}/messages",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"prompt": "continue"},
    )
    assert cross_1.status_code == 404

    cross_2 = await http_client.post(
        f"/v1/threads/{thread_a}/messages",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "continue"},
    )
    assert cross_2.status_code == 404
