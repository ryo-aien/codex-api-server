from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Unauthenticated liveness/readiness probe. Never returns secrets."""
    codex_service = getattr(request.app.state, "codex_service", None)
    database = getattr(request.app.state, "db", None)

    codex_status = "unavailable"
    authenticated = False
    if codex_service is not None:
        try:
            status_info = await codex_service.account_status()
            authenticated = bool(status_info.get("authenticated"))
            codex_status = "ready"
        except Exception:
            codex_status = "unavailable"

    database_status = "ready" if database is not None else "unavailable"

    return HealthResponse(
        status="ok",
        codex=codex_status,
        authenticated=authenticated,
        database=database_status,
    )
