from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, Request
from openai_codex.errors import CodexError

from app.codex.service import CodexServiceProtocol
from app.concurrency import JobLimiter
from app.config import Settings
from app.dependencies import (
    get_app_settings,
    get_codex_service,
    get_repository,
    require_auth,
)
from app.errors import (
    ConversationNotFoundError,
    InvalidRequestApiError,
    TimeoutApiError,
    map_codex_exception,
)
from app.repository import Repository
from app.schemas import (
    ChatConversationListItem,
    ChatConversationListResponse,
    ChatConversationResponse,
    ChatRequest,
    ChatResponse,
)
from app.security.principals import AuthenticatedPrincipal

logger = logging.getLogger("app.routes.chat")

router = APIRouter(tags=["chat"])


def get_job_limiter(request: Request) -> JobLimiter:
    return request.app.state.job_limiter


def _check_prompt_length(prompt: str, settings: Settings) -> None:
    if len(prompt) > settings.max_prompt_chars:
        raise InvalidRequestApiError(
            f"prompt exceeds maximum length of {settings.max_prompt_chars} characters"
        )


async def _require_owned_conversation(
    repo: Repository, conversation_id: str, principal: AuthenticatedPrincipal
):
    """Look up a conversation and enforce ownership (404 for non-owners)."""
    conv = await repo.get_conversation(conversation_id)
    if conv is None or conv.owner_client_id != principal.client_id:
        raise ConversationNotFoundError()
    return conv


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> ChatResponse:
    """One-shot chat: no repository, no history. Each call is independent."""
    _check_prompt_length(body.prompt, settings)

    request.state.audit_action = "chat"
    request.state.audit_prompt_chars = len(body.prompt)

    try:
        async with job_limiter.slot():
            outcome = await asyncio.wait_for(
                codex_service.chat(prompt=body.prompt),
                timeout=settings.codex_request_timeout,
            )
    except asyncio.TimeoutError as exc:
        request.state.audit_action = "timeout"
        request.state.audit_result_status = "timeout"
        raise TimeoutApiError() from exc
    except CodexError as exc:
        request.state.audit_result_status = "error"
        raise map_codex_exception(exc) from exc

    request.state.audit_result_status = outcome.status
    return ChatResponse(status=outcome.status, response=outcome.response)


@router.post("/v1/chat/conversations", response_model=ChatConversationResponse)
async def start_conversation(
    body: ChatRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> ChatConversationResponse:
    """Start a history-backed conversation. Returns a conversation_id.

    Send follow-ups to /v1/chat/conversations/{conversation_id}/messages;
    the server resumes this conversation automatically so context carries over.
    """
    _check_prompt_length(body.prompt, settings)

    request.state.audit_action = "chat_conversation_start"
    request.state.audit_prompt_chars = len(body.prompt)

    try:
        async with job_limiter.slot():
            outcome = await asyncio.wait_for(
                codex_service.chat_start(prompt=body.prompt),
                timeout=settings.codex_request_timeout,
            )
    except asyncio.TimeoutError as exc:
        request.state.audit_action = "timeout"
        request.state.audit_result_status = "timeout"
        raise TimeoutApiError() from exc
    except CodexError as exc:
        request.state.audit_result_status = "error"
        raise map_codex_exception(exc) from exc

    await repo.create_conversation(outcome.conversation_id, principal.client_id)

    request.state.audit_thread_id = outcome.conversation_id
    request.state.audit_turn_id = outcome.turn_id
    request.state.audit_result_status = outcome.status

    return ChatConversationResponse(
        conversation_id=outcome.conversation_id,
        status=outcome.status,
        response=outcome.response,
    )


@router.post(
    "/v1/chat/conversations/{conversation_id}/messages",
    response_model=ChatConversationResponse,
)
async def continue_conversation(
    conversation_id: str,
    body: ChatRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
    settings: Settings = Depends(get_app_settings),
    job_limiter: JobLimiter = Depends(get_job_limiter),
) -> ChatConversationResponse:
    """Continue an existing conversation (owner only). Send just the prompt."""
    _check_prompt_length(body.prompt, settings)
    await _require_owned_conversation(repo, conversation_id, principal)

    request.state.audit_action = "chat_conversation_message"
    request.state.audit_thread_id = conversation_id
    request.state.audit_prompt_chars = len(body.prompt)

    try:
        async with job_limiter.slot():
            outcome = await asyncio.wait_for(
                codex_service.chat_resume(conversation_id, prompt=body.prompt),
                timeout=settings.codex_request_timeout,
            )
    except asyncio.TimeoutError as exc:
        request.state.audit_action = "timeout"
        request.state.audit_result_status = "timeout"
        raise TimeoutApiError() from exc
    except CodexError as exc:
        request.state.audit_result_status = "error"
        raise map_codex_exception(exc) from exc

    await repo.touch_conversation(conversation_id, outcome.turn_id)

    request.state.audit_turn_id = outcome.turn_id
    request.state.audit_result_status = outcome.status

    return ChatConversationResponse(
        conversation_id=conversation_id,
        status=outcome.status,
        response=outcome.response,
    )


@router.get("/v1/chat/conversations", response_model=ChatConversationListResponse)
async def list_conversations(
    principal: AuthenticatedPrincipal = Depends(require_auth),
    repo: Repository = Depends(get_repository),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
) -> ChatConversationListResponse:
    """List the caller's own conversations (ownership enforced from SQLite)."""
    conversations = await repo.list_conversations_for_owner(
        principal.client_id, archived=archived, limit=limit, cursor=cursor
    )
    return ChatConversationListResponse(
        conversations=[
            ChatConversationListItem(
                conversation_id=c.conversation_id,
                created_at=c.created_at,
                updated_at=c.updated_at,
                archived=c.archived,
            )
            for c in conversations
        ]
    )
