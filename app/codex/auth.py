from __future__ import annotations

from openai_codex import AsyncCodex, CodexConfig

from app.config import Settings


def build_codex_config(settings: Settings) -> CodexConfig:
    """Build the CodexConfig used to launch the local Codex runtime.

    Auth mode selection happens after launch (see ``apply_auth_mode``): the
    Codex runtime itself decides where to look for credentials via its own
    ``CODEX_HOME`` (defaults to ``~/.codex``), which we persist through the
    ``codex-auth`` named volume in docker-compose.yml.
    """
    return CodexConfig()


async def apply_auth_mode(codex: AsyncCodex, settings: Settings) -> None:
    """Apply CODEX_AUTH_MODE at startup.

    - chatgpt (default): rely on the existing ChatGPT auth session persisted
      under the Codex home directory. Login is performed out-of-band via
      ``python -m cli.codex_auth login``.
    - api_key: log in with OPENAI_API_KEY as an explicit fallback.
    """
    if settings.codex_auth_mode == "api_key":
        if not settings.openai_api_key:
            raise RuntimeError(
                "CODEX_AUTH_MODE=api_key requires OPENAI_API_KEY to be set"
            )
        await codex.login_api_key(settings.openai_api_key)


async def get_account_status(codex: AsyncCodex) -> dict:
    """Return a minimal, credential-free summary of the backend Codex account."""
    try:
        response = await codex.account()
    except Exception:
        return {"authenticated": False, "auth_mode": None}

    account = response.account
    if account is None:
        return {"authenticated": False, "auth_mode": None}

    auth_mode = getattr(account.root, "type", None)
    return {"authenticated": True, "auth_mode": auth_mode}
