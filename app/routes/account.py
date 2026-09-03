from __future__ import annotations

from fastapi import APIRouter, Depends

from app.codex.service import CodexServiceProtocol
from app.dependencies import get_codex_service, require_auth
from app.schemas import AccountResponse
from app.security.principals import AuthenticatedPrincipal

router = APIRouter(tags=["account"])


@router.get("/v1/account", response_model=AccountResponse)
async def get_account(
    principal: AuthenticatedPrincipal = Depends(require_auth),
    codex_service: CodexServiceProtocol = Depends(get_codex_service),
) -> AccountResponse:
    status_info = await codex_service.account_status()
    return AccountResponse(
        authenticated=status_info.get("authenticated", False),
        auth_mode=status_info.get("auth_mode"),
    )
