from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import require_auth
from app.schemas import MeResponse
from app.security.principals import AuthenticatedPrincipal

router = APIRouter(tags=["me"])


@router.get("/v1/me", response_model=MeResponse)
async def get_me(
    principal: AuthenticatedPrincipal = Depends(require_auth),
) -> MeResponse:
    return MeResponse(
        client_id=principal.client_id,
        display_name=principal.display_name,
        role=principal.role,
        key_id=principal.key_id,
    )
