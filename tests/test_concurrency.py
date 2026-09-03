from __future__ import annotations

import asyncio

import pytest

from app.concurrency import JobLimiter
from app.errors import TooManyRequestsError
from tests.conftest import create_client_with_key


@pytest.mark.asyncio
async def test_job_limiter_allows_up_to_max():
    limiter = JobLimiter(2)
    async with limiter.slot():
        async with limiter.slot():
            assert True  # both slots acquired without error


@pytest.mark.asyncio
async def test_job_limiter_rejects_beyond_max():
    limiter = JobLimiter(1)
    async with limiter.slot():
        with pytest.raises(TooManyRequestsError):
            async with limiter.slot():
                pass


@pytest.mark.asyncio
async def test_job_limiter_releases_slot_after_use():
    limiter = JobLimiter(1)
    async with limiter.slot():
        pass
    async with limiter.slot():
        assert True  # slot was released and can be reacquired


@pytest.mark.asyncio
async def test_different_threads_can_run_concurrently(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")
    fake_codex_service.sleep_seconds = 0.05

    async def create_thread(prompt: str):
        return await http_client.post(
            "/v1/threads",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"repository": "project-a", "prompt": prompt},
        )

    results = await asyncio.gather(create_thread("task 1"), create_thread("task 2"))
    assert all(r.status_code == 200 for r in results)
    thread_ids = {r.json()["thread_id"] for r in results}
    assert len(thread_ids) == 2


@pytest.mark.asyncio
async def test_different_clients_share_global_limit(app_client, repo, test_settings, fake_codex_service):
    http_client, _app = app_client
    _a, alice_key, _ = await create_client_with_key(repo, test_settings, "alice")
    _b, bob_key, _ = await create_client_with_key(repo, test_settings, "bob")
    fake_codex_service.sleep_seconds = 0.2

    async def create_thread(raw_key: str, prompt: str):
        return await http_client.post(
            "/v1/threads",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"repository": "project-a", "prompt": prompt},
        )

    # test_settings.max_concurrent_jobs == 2; three concurrent requests from
    # two different clients must still share the single global limiter.
    results = await asyncio.gather(
        create_thread(alice_key, "alice task"),
        create_thread(bob_key, "bob task 1"),
        create_thread(bob_key, "bob task 2"),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 200, 429]
