from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from openai_codex import AsyncCodex
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.codex.auth import apply_auth_mode, build_codex_config
from app.codex.service import CodexService
from app.concurrency import JobLimiter
from app.config import get_settings
from app.db.connection import Database
from app.db.migrations import run_migrations
from app.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware import RequestContextMiddleware
from app.repository import Repository
from app.routes import account, health, me, threads

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    db = Database(settings.database_path)
    db.connect_sync()
    await db.run(run_migrations)
    repository = Repository(db)

    codex_config = build_codex_config(settings)
    async with AsyncCodex(codex_config) as codex:
        await apply_auth_mode(codex, settings)
        codex_service = CodexService(codex)

        app.state.settings = settings
        app.state.db = db
        app.state.repository = repository
        app.state.codex_service = codex_service
        app.state.job_limiter = JobLimiter(settings.max_concurrent_jobs)

        try:
            yield
        finally:
            db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="codex-api-server", lifespan=lifespan)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(
        RequestContextMiddleware,
        repository_factory=lambda: getattr(app.state, "repository", None),
    )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(account.router)
    app.include_router(threads.router)

    return app


app = create_app()
