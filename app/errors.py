from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openai_codex.errors import RetryLimitExceededError, ServerBusyError, TransportClosedError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Base application error mapped to a structured HTTP response."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "Unauthorized") -> None:
        # All API-key related failures are collapsed into a single
        # 401 unauthorized code so we never leak credential state details.
        super().__init__(401, "unauthorized", message)


class RepositoryNotFoundError(ApiError):
    def __init__(self, message: str = "Repository not found") -> None:
        super().__init__(404, "repository_not_found", message)


class ThreadNotFoundError(ApiError):
    def __init__(self, message: str = "Thread not found") -> None:
        super().__init__(404, "thread_not_found", message)


class ThreadBusyError(ApiError):
    def __init__(self, message: str = "Thread is busy") -> None:
        super().__init__(409, "thread_busy", message)


class ConversationNotFoundError(ApiError):
    def __init__(self, message: str = "Conversation not found") -> None:
        super().__init__(404, "conversation_not_found", message)


class InvalidRequestApiError(ApiError):
    def __init__(self, message: str = "Invalid request") -> None:
        super().__init__(400, "invalid_request", message)


class TooManyRequestsError(ApiError):
    def __init__(self, message: str = "Too many requests") -> None:
        super().__init__(429, "too_many_requests", message)


class CodexUnavailableError(ApiError):
    def __init__(self, message: str = "Codex backend is unavailable") -> None:
        super().__init__(503, "codex_unavailable", message)


class CodexUpstreamError(ApiError):
    def __init__(self, message: str = "Codex backend error") -> None:
        super().__init__(502, "codex_error", message)


class TimeoutApiError(ApiError):
    def __init__(self, message: str = "Request timed out") -> None:
        super().__init__(504, "timeout", message)


class InternalApiError(ApiError):
    def __init__(self, message: str = "Internal server error") -> None:
        super().__init__(500, "internal_error", message)


def map_codex_exception(exc: Exception) -> ApiError:
    """Map an openai_codex SDK exception to the appropriate HTTP error.

    ServerBusyError / RetryLimitExceededError / TransportClosedError mean the
    backend Codex runtime itself is temporarily unavailable (503). Any other
    CodexError (including turn failures such as missing/invalid backend
    credentials) is a bad response from the upstream Codex call (502).
    """
    if isinstance(exc, (ServerBusyError, RetryLimitExceededError, TransportClosedError)):
        return CodexUnavailableError(str(exc))
    return CodexUpstreamError(str(exc))


def _error_body(code: str, message: str, request_id: str | None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    request.state.audit_error_code = exc.code
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, _request_id(request)),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    request.state.audit_error_code = code
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, detail, _request_id(request)),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request.state.audit_error_code = "validation_error"
    return JSONResponse(
        status_code=422,
        content=_error_body("validation_error", "Request validation failed", _request_id(request)),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request.state.audit_error_code = "internal_error"
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "Internal server error", _request_id(request)),
    )
