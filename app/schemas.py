from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str
    codex: str
    authenticated: bool
    database: str


class MeResponse(BaseModel):
    client_id: str
    display_name: str | None
    role: str
    key_id: str


class AccountResponse(BaseModel):
    authenticated: bool
    auth_mode: str | None


class CreateThreadRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def _check_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return value


class ThreadMessageRequest(BaseModel):
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def _check_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return value


class ThreadResponse(BaseModel):
    thread_id: str
    turn_id: str
    repository: str
    status: str
    response: str | None


class ThreadListItem(BaseModel):
    thread_id: str
    repository: str
    created_at: str
    updated_at: str
    archived: bool


class ThreadListResponse(BaseModel):
    threads: list[ThreadListItem]


class ThreadArchiveResponse(BaseModel):
    thread_id: str
    archived: bool


class InterruptResponse(BaseModel):
    thread_id: str
    interrupted: bool
