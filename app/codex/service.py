from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from openai_codex import ApprovalMode, AsyncCodex, AsyncTurnHandle, Sandbox
from openai_codex import models as codex_models
from openai_codex.errors import CodexError

# openai_codex.AsyncThread.run()/turn() raise a plain RuntimeError (not a
# CodexError subclass) when a turn finishes with TurnStatus.failed, e.g. the
# backend Codex account is not authenticated. Route handlers only catch
# CodexError, so these are normalized to CodexError here at the single choke
# point where the SDK is invoked.
class CodexTurnFailedError(CodexError):
    pass

logger = logging.getLogger("app.codex")

# The installed SDK only exposes two approval modes (deny_all, auto_review).
# auto_review lets Codex proceed with sandboxed file writes / shell commands
# without a human in the loop, which is required for an unattended API
# server, while still keeping every action confined to Sandbox.workspace_write.
DEFAULT_APPROVAL_MODE = ApprovalMode.auto_review
DEFAULT_SANDBOX = Sandbox.workspace_write


@dataclass(frozen=True)
class TurnOutcome:
    thread_id: str
    turn_id: str
    status: str
    response: str | None


@dataclass(frozen=True)
class ChatOutcome:
    status: str
    response: str | None
    turn_id: str | None = None


@dataclass(frozen=True)
class ChatStartOutcome:
    conversation_id: str
    turn_id: str
    status: str
    response: str | None


class CodexServiceProtocol(Protocol):
    """Interface the routes depend on, so tests can substitute a fake."""

    async def chat(self, *, prompt: str) -> ChatOutcome: ...

    async def chat_start(self, *, prompt: str) -> ChatStartOutcome: ...

    async def chat_resume(self, conversation_id: str, *, prompt: str) -> ChatOutcome: ...

    async def start_thread(self, *, cwd: str, prompt: str) -> TurnOutcome: ...

    async def resume_thread(self, thread_id: str, *, cwd: str, prompt: str) -> TurnOutcome: ...

    def stream_turn(
        self, thread_id: str, *, cwd: str, prompt: str, resume: bool
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def interrupt_turn(self, thread_id: str) -> bool: ...

    async def archive_thread(self, thread_id: str) -> None: ...

    async def account_status(self) -> dict: ...


class TurnRegistry:
    """Tracks the in-flight AsyncTurnHandle for each thread so it can be interrupted."""

    def __init__(self) -> None:
        self._handles: dict[str, AsyncTurnHandle] = {}
        self._lock = asyncio.Lock()

    async def register(self, thread_id: str, handle: AsyncTurnHandle) -> None:
        async with self._lock:
            self._handles[thread_id] = handle

    async def unregister(self, thread_id: str) -> None:
        async with self._lock:
            self._handles.pop(thread_id, None)

    async def get(self, thread_id: str) -> AsyncTurnHandle | None:
        async with self._lock:
            return self._handles.get(thread_id)


class CodexService:
    """Wraps the OpenAI Codex Python SDK behind a small, testable interface.

    Responsible for: sandbox/approval enforcement, per-thread locking,
    normalizing SSE events, and mapping SDK exceptions.
    """

    def __init__(self, codex: AsyncCodex) -> None:
        self._codex = codex
        self._turn_registry = TurnRegistry()
        self._thread_locks: dict[str, asyncio.Lock] = {}
        self._thread_locks_guard = asyncio.Lock()

    async def _lock_for(self, thread_id: str) -> asyncio.Lock:
        async with self._thread_locks_guard:
            lock = self._thread_locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._thread_locks[thread_id] = lock
            return lock

    async def chat(self, *, prompt: str) -> ChatOutcome:
        """Plain conversational turn, not tied to any repository.

        Started without a working directory and with the most restrictive
        sandbox/approval so the model just answers instead of touching the
        filesystem or running commands. The thread is ephemeral: no ownership
        row is stored and it is not resumable via the /v1/threads endpoints.
        """
        thread = await self._codex.thread_start(
            sandbox=Sandbox.read_only,
            approval_mode=ApprovalMode.deny_all,
            ephemeral=True,
        )
        try:
            result = await thread.run(prompt)
        except RuntimeError as exc:
            raise CodexTurnFailedError(str(exc)) from exc
        return ChatOutcome(
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            response=result.final_response,
        )

    async def chat_start(self, *, prompt: str) -> ChatStartOutcome:
        """Start a history-backed chat conversation (no repository).

        Unlike chat(), this is NOT ephemeral: the thread persists so it can be
        resumed later via chat_resume(), giving the client a conversation that
        remembers previous turns. Still read-only / deny-all so it stays a
        plain chat and never touches the filesystem.
        """
        thread = await self._codex.thread_start(
            sandbox=Sandbox.read_only,
            approval_mode=ApprovalMode.deny_all,
        )
        lock = await self._lock_for(thread.id)
        async with lock:
            try:
                result = await thread.run(prompt)
            except RuntimeError as exc:
                raise CodexTurnFailedError(str(exc)) from exc
        return ChatStartOutcome(
            conversation_id=thread.id,
            turn_id=result.id,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            response=result.final_response,
        )

    async def chat_resume(self, conversation_id: str, *, prompt: str) -> ChatOutcome:
        """Continue an existing chat conversation so context carries over."""
        lock = await self._lock_for(conversation_id)
        async with lock:
            thread = await self._codex.thread_resume(
                conversation_id,
                sandbox=Sandbox.read_only,
                approval_mode=ApprovalMode.deny_all,
            )
            try:
                result = await thread.run(prompt)
            except RuntimeError as exc:
                raise CodexTurnFailedError(str(exc)) from exc
        return ChatOutcome(
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            response=result.final_response,
            turn_id=result.id,
        )

    async def start_thread(self, *, cwd: str, prompt: str) -> TurnOutcome:
        thread = await self._codex.thread_start(
            cwd=cwd,
            sandbox=DEFAULT_SANDBOX,
            approval_mode=DEFAULT_APPROVAL_MODE,
        )
        lock = await self._lock_for(thread.id)
        async with lock:
            try:
                result = await thread.run(prompt)
            except RuntimeError as exc:
                raise CodexTurnFailedError(str(exc)) from exc
        return TurnOutcome(
            thread_id=thread.id,
            turn_id=result.id,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            response=result.final_response,
        )

    async def resume_thread(self, thread_id: str, *, cwd: str, prompt: str) -> TurnOutcome:
        lock = await self._lock_for(thread_id)
        async with lock:
            thread = await self._codex.thread_resume(
                thread_id,
                cwd=cwd,
                sandbox=DEFAULT_SANDBOX,
                approval_mode=DEFAULT_APPROVAL_MODE,
            )
            try:
                result = await thread.run(prompt)
            except RuntimeError as exc:
                raise CodexTurnFailedError(str(exc)) from exc
        return TurnOutcome(
            thread_id=thread.id,
            turn_id=result.id,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            response=result.final_response,
        )

    async def stream_turn(
        self, thread_id: str | None, *, cwd: str, prompt: str, resume: bool
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield normalized SSE-ready event dicts for a streamed turn.

        If ``thread_id`` is None a new thread is started; otherwise the
        existing thread is resumed. Internal SDK notification types are never
        exposed directly to the client.
        """
        lock = await self._lock_for(thread_id) if thread_id else None
        if lock is not None:
            await lock.acquire()
        try:
            if thread_id is None or not resume:
                thread = await self._codex.thread_start(
                    cwd=cwd,
                    sandbox=DEFAULT_SANDBOX,
                    approval_mode=DEFAULT_APPROVAL_MODE,
                )
            else:
                thread = await self._codex.thread_resume(
                    thread_id,
                    cwd=cwd,
                    sandbox=DEFAULT_SANDBOX,
                    approval_mode=DEFAULT_APPROVAL_MODE,
                )

            if lock is None:
                lock = await self._lock_for(thread.id)
                await lock.acquire()

            yield {"event": "status", "data": {"status": "started", "thread_id": thread.id}}

            turn_handle = await thread.turn(prompt)
            await self._turn_registry.register(thread.id, turn_handle)
            final_turn_status: str | None = None
            final_turn_error: str | None = None
            try:
                async for notification in turn_handle.stream():
                    if isinstance(notification.payload, codex_models.TurnCompletedNotification):
                        turn = notification.payload.turn
                        final_turn_status = (
                            turn.status.value if hasattr(turn.status, "value") else str(turn.status)
                        )
                        if turn.error is not None:
                            final_turn_error = turn.error.message
                        continue
                    normalized = _normalize_notification(notification)
                    if normalized is not None:
                        yield normalized
            finally:
                await self._turn_registry.unregister(thread.id)

            if final_turn_status == "failed":
                yield {
                    "event": "error",
                    "data": {
                        "code": "codex_error",
                        "message": final_turn_error or "Turn failed",
                    },
                }
            else:
                yield {
                    "event": "completed",
                    "data": {
                        "thread_id": thread.id,
                        "turn_id": turn_handle.id,
                        "status": final_turn_status or "completed",
                    },
                }
        except (CodexError, RuntimeError) as exc:
            yield {"event": "error", "data": {"code": "codex_error", "message": str(exc)}}
        finally:
            if lock is not None and lock.locked():
                lock.release()

    async def interrupt_turn(self, thread_id: str) -> bool:
        handle = await self._turn_registry.get(thread_id)
        if handle is None:
            return False
        await handle.interrupt()
        return True

    async def archive_thread(self, thread_id: str) -> None:
        await self._codex.thread_archive(thread_id)

    async def account_status(self) -> dict:
        from app.codex.auth import get_account_status

        return await get_account_status(self._codex)


def _normalize_notification(notification: codex_models.Notification) -> dict[str, Any] | None:
    """Map an internal SDK notification to the small external SSE vocabulary.

    Reasoning / chain-of-thought events are intentionally dropped: only
    assistant text, tool status, and terminal events are exposed externally.
    """
    payload = notification.payload

    if isinstance(payload, codex_models.AgentMessageDeltaNotification):
        return {"event": "delta", "data": {"text": payload.delta}}

    if isinstance(payload, codex_models.ItemStartedNotification):
        return {"event": "tool", "data": {"status": "started", "item_type": _item_type(payload.item)}}

    if isinstance(payload, codex_models.ItemCompletedNotification):
        return {"event": "tool", "data": {"status": "completed", "item_type": _item_type(payload.item)}}

    if isinstance(payload, codex_models.TurnStartedNotification):
        return {"event": "status", "data": {"status": "turn_started"}}

    if isinstance(payload, codex_models.ErrorNotification):
        message = getattr(payload.error, "message", str(payload.error))
        return {"event": "error", "data": {"code": "codex_error", "message": message}}

    # TurnCompletedNotification is handled by the caller emitting its own
    # "completed" event once turn_handle.stream() is exhausted; reasoning,
    # token usage, and other internal notifications are not forwarded.
    return None


def _item_type(item: Any) -> str:
    # ThreadItem is a pydantic RootModel wrapping a discriminated union of
    # concrete *ThreadItem classes; unwrap .root to reach the "type" field.
    unwrapped = getattr(item, "root", item)
    return getattr(unwrapped, "type", None) or type(unwrapped).__name__
