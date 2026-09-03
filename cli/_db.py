from __future__ import annotations

import sqlite3

from app.config import get_settings
from app.db.connection import connect
from app.db.migrations import run_migrations


def open_db() -> sqlite3.Connection:
    settings = get_settings()
    conn = connect(settings.database_path)
    run_migrations(conn)
    return conn
