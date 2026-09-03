from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.db.audit import new_entry

logger = logging.getLogger("app.request")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _client_request_id(request: Request) -> str | None:
    value = request.headers.get("X-Request-ID")
    if value and _REQUEST_ID_PATTERN.match(value):
        return value
    return None


def _remote_ip(request: Request) -> str | None:
    """Return the direct connection's remote IP.

    Deliberately ignores X-Forwarded-For by default: this server does not
    assume a reverse proxy, and that header is trivially spoofable by any
    LAN client. A trusted-proxy allowlist can be added later if needed.
    """
    client = request.client
    return client.host if client else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, and writes one audit row.

    The audit row captures only metadata (never prompt/response bodies,
    never Authorization headers) per the audit policy in app/db/audit.py.
    """

    def __init__(self, app, repository_factory) -> None:
        super().__init__(app)
        self._repository_factory = repository_factory

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _client_request_id(request) or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.auth_failure = False
        started = time.monotonic()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = int((time.monotonic() - started) * 1000)
            await self._audit(request, 500, duration_ms, "internal_error")
            raise

        duration_ms = int((time.monotonic() - started) * 1000)
        response.headers["X-Request-ID"] = request_id

        if request.url.path != "/health":
            error_code = getattr(request.state, "audit_error_code", None)
            await self._audit(request, status_code, duration_ms, error_code)

        return response

    async def _audit(
        self, request: Request, status_code: int, duration_ms: int, error_code: str | None
    ) -> None:
        principal = getattr(request.state, "principal", None)
        action = getattr(request.state, "audit_action", None) or _default_action(request)

        entry = new_entry(
            action=action,
            request_id=getattr(request.state, "request_id", None),
            client_id=principal.client_id if principal else None,
            key_id=principal.key_id if principal else None,
            method=request.method,
            path=request.url.path,
            repository=getattr(request.state, "audit_repository", None),
            thread_id=getattr(request.state, "audit_thread_id", None),
            turn_id=getattr(request.state, "audit_turn_id", None),
            status_code=status_code,
            duration_ms=duration_ms,
            remote_ip=_remote_ip(request),
            user_agent=request.headers.get("user-agent"),
            prompt_chars=getattr(request.state, "audit_prompt_chars", None),
            result_status=getattr(request.state, "audit_result_status", None),
            error_code=error_code,
        )

        try:
            repo = self._repository_factory()
            if repo is not None:
                await repo.insert_audit_log(entry)
        except Exception:
            logger.exception("Failed to write audit log entry")


def _default_action(request: Request) -> str:
    if getattr(request.state, "auth_failure", False):
        return "authentication_failure"
    return f"{request.method} {request.url.path}"
