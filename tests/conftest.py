from __future__ import annotations

import asyncio
import itertools
import os
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("API_KEY_PEPPER", "test-pepper-0123456789abcdef")
os.environ.setdefault("CODEX_AUTH_MODE", "chatgpt")

from app.codex.service import ChatOutcome, ChatStartOutcome, TurnOutcome
from app.concurrency import JobLimiter
from app.config import Settings
from app.db.connection import Database
from app.db.migrations import run_migrations
from app.repository import Repository
from app.security.api_keys import generate_key_id, generate_raw_api_key, hash_api_key


class FakeTurnHandle:
    def __init__(self, thread_id: str, turn_id: str, events: list[dict], delay: float = 0.0):
        self.thread_id = thread_id
        self.id = turn_id
        self._events = events
        self._delay = delay
        self.interrupted = False

    async def stream(self) -> AsyncIterator[dict]:
        for event in self._events:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield event

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeCodexService:
    """Test double implementing CodexServiceProtocol without touching the SDK."""

    def __init__(self) -> None:
        self._thread_counter = itertools.count(1)
        self._turn_counter = itertools.count(1)
        self.sleep_seconds: float = 0.0
        self.fail_with: Exception | None = None
        self.interrupted_threads: set[str] = set()
        self._account_status = {"authenticated": True, "auth_mode": "chatgpt"}
        # conversation_id -> list of prompts, so tests can assert that resume
        # carries prior context.
        self.conversations: dict[str, list[str]] = {}

    def _new_thread_id(self) -> str:
        return f"thr_{next(self._thread_counter):06d}"

    def _new_turn_id(self) -> str:
        return f"turn_{next(self._turn_counter):06d}"

    async def chat(self, *, prompt: str) -> ChatOutcome:
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.fail_with:
            raise self.fail_with
        return ChatOutcome(status="completed", response=f"reply: {prompt[:50]}")

    async def chat_start(self, *, prompt: str) -> ChatStartOutcome:
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.fail_with:
            raise self.fail_with
        conversation_id = self._new_thread_id()
        self.conversations[conversation_id] = [prompt]
        return ChatStartOutcome(
            conversation_id=conversation_id,
            turn_id=self._new_turn_id(),
            status="completed",
            response=f"reply: {prompt[:50]}",
        )

    async def chat_resume(self, conversation_id: str, *, prompt: str) -> ChatOutcome:
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.fail_with:
            raise self.fail_with
        history = self.conversations.setdefault(conversation_id, [])
        history.append(prompt)
        # Echo how many turns this conversation has seen, so tests can assert
        # that context (the prior turns) is retained across resume.
        return ChatOutcome(
            status="completed",
            response=f"reply({len(history)} turns): {prompt[:50]}",
            turn_id=self._new_turn_id(),
        )

    async def start_thread(self, *, cwd: str, prompt: str) -> TurnOutcome:
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.fail_with:
            raise self.fail_with
        thread_id = self._new_thread_id()
        return TurnOutcome(
            thread_id=thread_id,
            turn_id=self._new_turn_id(),
            status="completed",
            response=f"processed: {prompt[:50]}",
        )

    async def resume_thread(self, thread_id: str, *, cwd: str, prompt: str) -> TurnOutcome:
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        if self.fail_with:
            raise self.fail_with
        return TurnOutcome(
            thread_id=thread_id,
            turn_id=self._new_turn_id(),
            status="completed",
            response=f"processed: {prompt[:50]}",
        )

    async def stream_turn(
        self, thread_id: str | None, *, cwd: str, prompt: str, resume: bool
    ) -> AsyncIterator[dict[str, Any]]:
        resolved_id = thread_id or self._new_thread_id()
        turn_id = self._new_turn_id()

        yield {"event": "status", "data": {"status": "started", "thread_id": resolved_id}}

        for _ in range(2):
            if self.sleep_seconds:
                await asyncio.sleep(self.sleep_seconds)
            if resolved_id in self.interrupted_threads:
                yield {"event": "error", "data": {"code": "interrupted", "message": "interrupted"}}
                return
            yield {"event": "delta", "data": {"text": f"chunk for {prompt[:20]}"}}

        yield {
            "event": "completed",
            "data": {"thread_id": resolved_id, "turn_id": turn_id, "status": "completed"},
        }

    async def interrupt_turn(self, thread_id: str) -> bool:
        self.interrupted_threads.add(thread_id)
        return True

    async def archive_thread(self, thread_id: str) -> None:
        return None

    async def account_status(self) -> dict:
        return self._account_status


@pytest.fixture
def test_settings(tmp_path) -> Settings:
    db_path = tmp_path / "test.db"
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    (workspace_root / "project-a").mkdir()

    return Settings(
        api_key_pepper="test-pepper-0123456789abcdef",
        database_path=str(db_path),
        workspace_root=str(workspace_root),
        max_concurrent_jobs=2,
        codex_request_timeout=5,
        max_prompt_chars=1000,
        cors_origins="",
    )


@pytest_asyncio.fixture
async def db(test_settings: Settings) -> Database:
    database = Database(test_settings.database_path)
    database.connect_sync()
    await database.run(run_migrations)
    yield database
    database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


@pytest.fixture
def fake_codex_service() -> FakeCodexService:
    return FakeCodexService()


@pytest_asyncio.fixture
async def app_client(test_settings: Settings, db: Database, repo: Repository, fake_codex_service: FakeCodexService):
    from app.dependencies import get_app_settings
    from app.main import create_app

    app = create_app()

    # Bypass the real lifespan (which would start a real AsyncCodex process)
    # and wire up test doubles + the already-migrated test database instead.
    app.state.settings = test_settings
    app.state.db = db
    app.state.repository = repo
    app.state.codex_service = fake_codex_service
    app.state.job_limiter = JobLimiter(test_settings.max_concurrent_jobs)

    app.dependency_overrides[get_app_settings] = lambda: test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, app


async def create_client_with_key(repo: Repository, test_settings: Settings, client_id: str, role: str = "user"):
    client_record = await repo.create_client(client_id, client_id.capitalize(), role)
    raw_key = generate_raw_api_key()
    key_id = generate_key_id()
    key_hash = hash_api_key(raw_key, test_settings.api_key_pepper)
    await repo.create_api_key(client_record.id, key_id, key_hash)
    return client_record, raw_key, key_id
