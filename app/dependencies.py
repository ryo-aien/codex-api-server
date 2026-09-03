from __future__ import annotations

import re
from pathlib import Path

from fastapi import Depends, Header, Request

from app.codex.service import CodexServiceProtocol
from app.config import Settings, get_settings
from app.errors import RepositoryNotFoundError, UnauthorizedError
from app.repository import Repository
from app.security.api_keys import hash_api_key
from app.security.principals import AuthenticatedPrincipal

REPOSITORY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_REJECTED_REPOSITORY_NAMES = {".", ".."}


class InvalidRepositoryNameError(Exception):
    pass


def validate_repository_name(name: str) -> None:
    if name in _REJECTED_REPOSITORY_NAMES:
        raise InvalidRepositoryNameError("Repository name must not be '.' or '..'")
    if "/" in name or "\\" in name:
        raise InvalidRepositoryNameError("Repository name must not contain path separators")
    if not REPOSITORY_NAME_PATTERN.match(name):
        raise InvalidRepositoryNameError(
            "Repository name must match ^[A-Za-z0-9._-]+$"
        )


def resolve_repository_path(workspace_root: str, repository: str) -> Path:
    """Resolve a repository name to an absolute path confined to WORKSPACE_ROOT.

    Rejects path traversal and symlink escapes by resolving both the root
    and the candidate path and checking containment after resolution.
    """
    try:
        validate_repository_name(repository)
    except InvalidRepositoryNameError as exc:
        raise RepositoryNotFoundError(str(exc)) from exc

    root = Path(workspace_root).resolve()
    candidate = (root / repository).resolve()

    if candidate != root and root not in candidate.parents:
        raise RepositoryNotFoundError("Repository not found")

    if not candidate.is_dir():
        raise RepositoryNotFoundError("Repository not found")

    return candidate


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_codex_service(request: Request) -> CodexServiceProtocol:
    return request.app.state.codex_service


def get_app_settings() -> Settings:
    return get_settings()


_BEARER_PREFIX = "Bearer "


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_app_settings),
) -> AuthenticatedPrincipal:
    """Verify the client's API key and resolve it to a principal.

    All failure modes collapse to a single 401 unauthorized to avoid leaking
    credential state (disabled vs revoked vs expired vs malformed).
    """
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        request.state.auth_failure = True
        raise UnauthorizedError()

    raw_key = authorization[len(_BEARER_PREFIX) :].strip()
    if not raw_key:
        request.state.auth_failure = True
        raise UnauthorizedError()

    key_hash = hash_api_key(raw_key, settings.api_key_pepper)
    lookup = await repo.find_api_key_by_hash(key_hash)

    if lookup is None:
        request.state.auth_failure = True
        raise UnauthorizedError()

    api_key = lookup.api_key

    if not api_key.enabled or api_key.revoked_at is not None:
        request.state.auth_failure = True
        raise UnauthorizedError()

    if api_key.expires_at is not None:
        from datetime import datetime, timezone

        expires_at = datetime.fromisoformat(api_key.expires_at)
        if expires_at <= datetime.now(timezone.utc):
            request.state.auth_failure = True
            raise UnauthorizedError()

    if not lookup.client_enabled:
        request.state.auth_failure = True
        raise UnauthorizedError()

    await repo.touch_api_key_last_used(api_key.key_id)

    principal = AuthenticatedPrincipal(
        client_id=lookup.client_id,
        display_name=lookup.display_name,
        role=lookup.role,
        key_id=api_key.key_id,
    )
    request.state.principal = principal
    return principal
