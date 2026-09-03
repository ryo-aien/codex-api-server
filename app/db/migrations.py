from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        schema_version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT NOT NULL UNIQUE,
        display_name TEXT,
        role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_db_id INTEGER NOT NULL REFERENCES clients(id),
        key_id TEXT NOT NULL UNIQUE,
        key_hash TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        expires_at TEXT,
        revoked_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_client_db_id ON api_keys(client_db_id)",
    """
    CREATE TABLE IF NOT EXISTS codex_threads (
        thread_id TEXT PRIMARY KEY,
        owner_client_id TEXT NOT NULL,
        repository TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0,
        last_turn_id TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_codex_threads_owner ON codex_threads(owner_client_id)",
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        request_id TEXT,
        client_id TEXT,
        key_id TEXT,
        action TEXT NOT NULL,
        method TEXT,
        path TEXT,
        repository TEXT,
        thread_id TEXT,
        turn_id TEXT,
        status_code INTEGER,
        duration_ms INTEGER,
        remote_ip TEXT,
        user_agent TEXT,
        prompt_chars INTEGER,
        result_status TEXT,
        error_code TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_client_id ON audit_logs(client_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_repository ON audit_logs(repository)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)",
    # schema v2: history-backed chat conversations (no repository; not tied to
    # a workspace). Separate from codex_threads so the agent endpoints and the
    # plain-chat endpoints never mix.
    """
    CREATE TABLE IF NOT EXISTS chat_conversations (
        conversation_id TEXT PRIMARY KEY,
        owner_client_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0,
        last_turn_id TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_conversations_owner ON chat_conversations(owner_client_id)",
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """Create tables if needed and stamp the schema version.

    This project does not use an external migration framework. Schema
    changes going forward should extend this function with version-gated
    ALTER TABLE statements driven off ``schema_meta.schema_version``.
    """
    with conn:
        for statement in _SCHEMA_STATEMENTS:
            conn.execute(statement)

        row = conn.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_meta (id, schema_version) VALUES (1, ?)",
                (SCHEMA_VERSION,),
            )
        elif row["schema_version"] < SCHEMA_VERSION:
            # All statements above are CREATE TABLE/INDEX IF NOT EXISTS, so
            # re-running them on an existing DB only adds the new objects.
            # Bump the recorded version to match.
            conn.execute(
                "UPDATE schema_meta SET schema_version = ? WHERE id = 1",
                (SCHEMA_VERSION,),
            )
