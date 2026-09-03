from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.codex.service import CodexServiceProtocol
from app.concurrency import JobLimiter
from app.config import Settings
from app.dependencies import (
    get_app_settings,
    get_codex_service,
    get_repository,
    require_auth,
    resolve_repository_path,
)
from app.errors import (
    InvalidRequestApiError,
    ThreadNotFoundError,
    TimeoutApiError,
    map_codex_exception,
)
from app.repository import Repository
from app.schemas import (
    CreateThreadRequest,
    InterruptResponse,
    ThreadArchiveResponse,
    ThreadListItem,
    ThreadListResponse,
    ThreadMessageRequest,
    ThreadResponse,
)
from app.security.principals import AuthenticatedPrincipal
from openai_codex.errors import CodexError

logger = logging.getLogger("app.routes.threads")

router = APIRouter(tags=["threads"])


def get_job_limiter(request: Request) -> JobLimiter:
    return request.app.state.job_limiter


def _mark_audit(
    request: Request,
    *,
    action: str,
    repository: str | None = None,
    thread_id: str | None = None,
    turn_id: str | None = None,
    prompt_chars: int | None = None,
    result_status: str | None = None,
) -> None:
    request.state.audit_action = action
    if repository is not None:
        request.state.audit_repository = repository
    if thread_id is not None:
        request.state.audit_thread_id = thread_id
    if turn_id is not None:
        request.state.audit_turn_id = turn_id
    if prompt_chars is not None:
        request.state.audit_prompt_chars = prompt_chars
    if result_status is not None:
        request.state.audit_result_status = result_status


def _validate_prompt_length(prompt: str, settings: Settings) -> None:
    if len(prompt) > settings.max_prompt_chars:
        raise InvalidRequestApiError(
            f"prompt exceeds maximum length of {settings.max_prompt_chars} characters"
        )


async def _require_owned_thread(repo: Repository, thread_id: str, principal: AuthenticatedPrincipal):
    """Look up a thread and enforce ownership.

    Returns 404 (never 403) when the thread does not exist or is not owned
    by the caller, so thread-id existence is never leaked to non-owners.
    """
    thread = await repo.get_thread(thread_id)
    if thread is None or thread.owner_client_id != principal.client_id:
        raise ThreadNotFoundError()
    return thread


@router.post("/v1/threads", response_model=ThreadResponse)
async def create_thread(
    body: CreateThreadRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> ThreadResponse:
    _validate_prompt_length(body.prompt, settings)
    resolved_path = resolve_repository_path(settings.workspace_root, body.repository)

    _mark_audit(
        request,
        action="thread_create",
        repository=body.repository,
        prompt_chars=len(body.prompt),
    )

    try:
        async with job_limiter.slot():
            outcome = await asyncio.wait_for(
                codex_service.start_thread(cwd=str(resolved_path), prompt=body.prompt),
                timeout=settings.codex_request_timeout,
            )
    except asyncio.TimeoutError as exc:
        _mark_audit(request, action="timeout", result_status="timeout")
        raise TimeoutApiError() from exc
    except CodexError as exc:
        _mark_audit(request, action="thread_create", result_status="error")
        raise map_codex_exception(exc) from exc

    await repo.create_thread(outcome.thread_id, principal.client_id, body.repository)

    _mark_audit(
        request,
        action="thread_create",
        thread_id=outcome.thread_id,
        turn_id=outcome.turn_id,
        result_status=outcome.status,
    )

    return ThreadResponse(
        thread_id=outcome.thread_id,
        turn_id=outcome.turn_id,
        repository=body.repository,
        status=outcome.status,
        response=outcome.response,
    )


@router.post("/v1/threads/{thread_id}/messages", response_model=ThreadResponse)
async def post_message(
    thread_id: str,
    body: ThreadMessageRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> ThreadResponse:
    _validate_prompt_length(body.prompt, settings)
    thread = await _require_owned_thread(repo, thread_id, principal)
    resolved_path = resolve_repository_path(settings.workspace_root, thread.repository)

    _mark_audit(
        request,
        action="thread_resume",
        repository=thread.repository,
        thread_id=thread_id,
        prompt_chars=len(body.prompt),
    )

    try:
        async with job_limiter.slot():
            outcome = await asyncio.wait_for(
                codex_service.resume_thread(thread_id, cwd=str(resolved_path), prompt=body.prompt),
                timeout=settings.codex_request_timeout,
            )
    except asyncio.TimeoutError as exc:
        _mark_audit(request, action="timeout", thread_id=thread_id, result_status="timeout")
        raise TimeoutApiError() from exc
    except CodexError as exc:
        _mark_audit(request, action="thread_resume", thread_id=thread_id, result_status="error")
        raise map_codex_exception(exc) from exc

    await repo.touch_thread(thread_id, outcome.turn_id)

    _mark_audit(
        request,
        action="thread_resume",
        thread_id=thread_id,
        turn_id=outcome.turn_id,
        result_status=outcome.status,
    )

    return ThreadResponse(
        thread_id=outcome.thread_id,
        turn_id=outcome.turn_id,
        repository=thread.repository,
        status=outcome.status,
        response=outcome.response,
    )


@router.get("/v1/threads", response_model=ThreadListResponse)
async def list_threads(
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
) -> ThreadListResponse:
    # Ownership is always enforced from SQLite, regardless of what the
    # underlying Codex SDK's thread_list() would otherwise return.
    threads = await repo.list_threads_for_owner(
        principal.client_id, archived=archived, limit=limit, cursor=cursor
    )
    return ThreadListResponse(
        threads=[
            ThreadListItem(
                thread_id=t.thread_id,
                repository=t.repository,
                created_at=t.created_at,
                updated_at=t.updated_at,
                archived=t.archived,
            )
            for t in threads
        ]
    )


@router.delete("/v1/threads/{thread_id}", response_model=ThreadArchiveResponse)
async def delete_thread(
    thread_id: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
) -> ThreadArchiveResponse:
    await _require_owned_thread(repo, thread_id, principal)

    _mark_audit(request, action="thread_archive", thread_id=thread_id)

    try:
        await codex_service.archive_thread(thread_id)
    except CodexError as exc:
        raise map_codex_exception(exc) from exc

    await repo.archive_thread(thread_id)

    return ThreadArchiveResponse(thread_id=thread_id, archived=True)


@router.post("/v1/threads/{thread_id}/interrupt", response_model=InterruptResponse)
async def interrupt_thread(
    thread_id: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
) -> InterruptResponse:
    await _require_owned_thread(repo, thread_id, principal)

    _mark_audit(request, action="interrupt", thread_id=thread_id)

    interrupted = await codex_service.interrupt_turn(thread_id)
    return InterruptResponse(thread_id=thread_id, interrupted=interrupted)


def _sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_response(
    generator: AsyncIterator[dict],
    *,
    timeout: int,
    request: Request,
    repo: Repository,
    thread_id: str | None,
    owner_client_id: str,
    repository_name: str,
) -> AsyncIterator[str]:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    iterator = generator.__aiter__()
    resolved_thread_id = thread_id

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                _mark_audit(request, action="timeout", result_status="timeout")
                yield _sse_format("error", {"code": "timeout", "message": "Request timed out"})
                return

            try:
                event = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                _mark_audit(request, action="timeout", result_status="timeout")
                yield _sse_format("error", {"code": "timeout", "message": "Request timed out"})
                return

            if event["event"] == "status" and "thread_id" in event.get("data", {}):
                resolved_thread_id = event["data"]["thread_id"]

            if event["event"] == "completed":
                new_thread_id = event["data"].get("thread_id", resolved_thread_id)
                if thread_id is None and new_thread_id:
                    await repo.create_thread(new_thread_id, owner_client_id, repository_name)
                elif new_thread_id:
                    await repo.touch_thread(new_thread_id, event["data"].get("turn_id"))
                _mark_audit(
                    request,
                    action="stream_execution",
                    thread_id=new_thread_id,
                    result_status="completed",
                )

            if event["event"] == "error":
                _mark_audit(
                    request,
                    action="stream_execution",
                    thread_id=resolved_thread_id,
                    result_status="error",
                )

            yield _sse_format(event["event"], event["data"])
    except CodexError as exc:
        mapped = map_codex_exception(exc)
        yield _sse_format("error", {"code": mapped.code, "message": mapped.message})


@router.post("/v1/threads/stream")
async def stream_new_thread(
    body: CreateThreadRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> StreamingResponse:
    _validate_prompt_length(body.prompt, settings)
    resolved_path = resolve_repository_path(settings.workspace_root, body.repository)

    _mark_audit(
        request,
        action="stream_execution",
        repository=body.repository,
        prompt_chars=len(body.prompt),
    )

    async def event_source() -> AsyncIterator[str]:
        async with job_limiter.slot():
            generator = codex_service.stream_turn(
                None, cwd=str(resolved_path), prompt=body.prompt, resume=False
            )
            async for chunk in _stream_response(
                generator,
                timeout=settings.codex_request_timeout,
                request=request,
                repo=repo,
                thread_id=None,
                owner_client_id=principal.client_id,
                repository_name=body.repository,
            ):
                yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/v1/threads/{thread_id}/stream")
async def stream_existing_thread(
    thread_id: str,
    body: ThreadMessageRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> StreamingResponse:
    _validate_prompt_length(body.prompt, settings)
    thread = await _require_owned_thread(repo, thread_id, principal)
    resolved_path = resolve_repository_path(settings.workspace_root, thread.repository)

    _mark_audit(
        request,
        action="stream_execution",
        repository=thread.repository,
        thread_id=thread_id,
        prompt_chars=len(body.prompt),
    )

    async def event_source() -> AsyncIterator[str]:
        async with job_limiter.slot():
            generator = codex_service.stream_turn(
                thread_id, cwd=str(resolved_path), prompt=body.prompt, resume=True
            )
            async for chunk in _stream_response(
                generator,
                timeout=settings.codex_request_timeout,
                request=request,
                repo=repo,
                thread_id=thread_id,
                owner_client_id=principal.client_id,
                repository_name=thread.repository,
            ):
                yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")
