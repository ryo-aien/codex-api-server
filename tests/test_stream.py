from __future__ import annotations

import pytest

from tests.conftest import create_client_with_key


async def _collect_sse_events(response) -> list[tuple[str, str]]:
    events = []
    current_event = None
    async for line in response.aiter_lines():
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((current_event, line[len("data: "):]))
    return events


@pytest.mark.asyncio
async def test_stream_new_thread_emits_normalized_events(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    async with http_client.stream(
        "POST",
        "/v1/threads/stream",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "stream this"},
    ) as response:
        assert response.status_code == 200
        events = await _collect_sse_events(response)

    event_names = [name for name, _ in events]
    assert "status" in event_names
    assert "delta" in event_names
    assert "completed" in event_names
    # Internal reasoning/thinking events must never be forwarded.
    assert "reasoning" not in event_names


@pytest.mark.asyncio
async def test_stream_existing_thread_requires_ownership(app_client, repo, test_settings):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")

    created = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"repository": "project-a", "prompt": "alice's thread"},
    )
    thread_id = created.json()["thread_id"]

    response = await http_client.post(
        f"/v1/threads/{thread_id}/stream",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"prompt": "steal"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_emits_error_event_on_timeout(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    test_settings.codex_request_timeout = 0
    fake_codex_service.sleep_seconds = 0.2

    async with http_client.stream(
        "POST",
        "/v1/threads/stream",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "this will time out"},
    ) as response:
        assert response.status_code == 200
        events = await _collect_sse_events(response)

    event_names = [name for name, _ in events]
    assert "error" in event_names
    error_payloads = [data for name, data in events if name == "error"]
    assert any("timeout" in payload for payload in error_payloads)


@pytest.mark.asyncio
async def test_interrupt_running_thread(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    created = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "long running task"},
    )
    thread_id = created.json()["thread_id"]

    response = await http_client.post(
        f"/v1/threads/{thread_id}/interrupt",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200
    assert response.json()["interrupted"] is True
    assert thread_id in fake_codex_service.interrupted_threads
