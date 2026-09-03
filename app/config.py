from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # FastAPI / LAN
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # SQLite
    database_path: str = Field(default="/data/codex-api.db", alias="DATABASE_PATH")

    # HMAC pepper used to hash API keys before storing them in SQLite.
    api_key_pepper: str = Field(alias="API_KEY_PEPPER")

    # Codex authentication
    codex_auth_mode: str = Field(default="chatgpt", alias="CODEX_AUTH_MODE")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Workspace
    workspace_root: str = Field(default="/workspaces", alias="WORKSPACE_ROOT")

    # Limits
    max_concurrent_jobs: int = Field(default=2, alias="MAX_CONCURRENT_JOBS")
    codex_request_timeout: int = Field(default=900, alias="CODEX_REQUEST_TIMEOUT")
    max_prompt_chars: int = Field(default=100_000, alias="MAX_PROMPT_CHARS")

    # Browser access
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Trusted proxy support is intentionally off by default. Do not trust
    # X-Forwarded-For unless explicitly enabled by a future change.
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")

    @field_validator("codex_auth_mode")
    @classmethod
    def _validate_auth_mode(cls, value: str) -> str:
        if value not in {"chatgpt", "api_key"}:
            raise ValueError("CODEX_AUTH_MODE must be 'chatgpt' or 'api_key'")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
