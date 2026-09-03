from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.errors import TooManyRequestsError


class JobLimiter:
    """Global cap on concurrent Codex turns across all clients.

    Deliberately global (not per-client): the backend Codex/ChatGPT account
    is shared across every client_id, so limiting concurrency per-client
    would let the aggregate exceed what the backend account can sustain.
    A MAX_CONCURRENT_JOBS_PER_CLIENT layer can be added later without
    changing this interface.

    Requests that arrive once capacity is full fail fast with 429 rather
    than queuing indefinitely behind an asyncio.Semaphore.
    """

    def __init__(self, max_concurrent_jobs: int) -> None:
        self._max = max_concurrent_jobs
        self._in_use = 0
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            if self._in_use >= self._max:
                raise TooManyRequestsError("Server is at maximum concurrent job capacity")
            self._in_use += 1
        try:
            yield
        finally:
            async with self._lock:
                self._in_use -= 1
