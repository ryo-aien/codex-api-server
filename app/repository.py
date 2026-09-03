from __future__ import annotations

from app.db import api_keys as api_keys_db
from app.db import audit as audit_db
from app.db import chat as chat_db
from app.db import clients as clients_db
from app.db import threads as threads_db
from app.db.connection import Database


class Repository:
    """Async facade over the SQLite access modules.

    Route and service code should depend on this class rather than reaching
    into ``app.db.*`` directly, and never hold a transaction open across a
    Codex SDK call.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # -- clients ---------------------------------------------------------

    async def create_client(
        self, client_id: str, display_name: str | None, role: str = "user"
    ) -> clients_db.ClientRecord:
        return await self._db.run(clients_db.create_client, client_id, display_name, role)

    async def get_client(self, client_id: str) -> clients_db.ClientRecord | None:
        return await self._db.run(clients_db.get_client, client_id)

    async def list_clients(self) -> list[clients_db.ClientRecord]:
        return await self._db.run(clients_db.list_clients)

    async def set_client_enabled(self, client_id: str, enabled: bool) -> clients_db.ClientRecord:
        return await self._db.run(clients_db.set_enabled, client_id, enabled)

    # -- api keys ----------------------------------------------------------

    async def create_api_key(
        self,
        client_db_id: int,
        key_id: str,
        key_hash: str,
        expires_in_days: int | None = None,
    ) -> api_keys_db.ApiKeyRecord:
        return await self._db.run(
            api_keys_db.create_api_key, client_db_id, key_id, key_hash, expires_in_days
        )

    async def find_api_key_by_hash(self, key_hash: str) -> api_keys_db.ApiKeyLookupResult | None:
        return await self._db.run(api_keys_db.find_by_hash, key_hash)

    async def touch_api_key_last_used(self, key_id: str) -> None:
        await self._db.run(api_keys_db.touch_last_used, key_id)

    async def list_api_keys_by_client(self, client_db_id: int) -> list[api_keys_db.ApiKeyRecord]:
        return await self._db.run(api_keys_db.list_by_client, client_db_id)

    async def get_api_key_by_key_id(self, key_id: str) -> api_keys_db.ApiKeyRecord | None:
        return await self._db.run(api_keys_db.get_by_key_id, key_id)

    async def revoke_api_key(self, key_id: str) -> api_keys_db.ApiKeyRecord:
        return await self._db.run(api_keys_db.revoke, key_id)

    async def set_api_key_enabled(self, key_id: str, enabled: bool) -> api_keys_db.ApiKeyRecord:
        return await self._db.run(api_keys_db.set_enabled, key_id, enabled)

    # -- threads -----------------------------------------------------------

    async def create_thread(
        self, thread_id: str, owner_client_id: str, repository: str
    ) -> threads_db.ThreadRecord:
        return await self._db.run(
            threads_db.create_thread, thread_id, owner_client_id, repository
        )

    async def get_thread(self, thread_id: str) -> threads_db.ThreadRecord | None:
        return await self._db.run(threads_db.get_thread, thread_id)

    async def touch_thread(self, thread_id: str, last_turn_id: str | None) -> None:
        await self._db.run(threads_db.touch_thread, thread_id, last_turn_id)

    async def archive_thread(self, thread_id: str) -> threads_db.ThreadRecord:
        return await self._db.run(threads_db.archive_thread, thread_id)

    async def list_threads_for_owner(
        self,
        owner_client_id: str,
        *,
        archived: bool | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[threads_db.ThreadRecord]:
        return await self._db.run(
            threads_db.list_threads_for_owner,
            owner_client_id,
            archived=archived,
            limit=limit,
            cursor=cursor,
        )

    # -- chat conversations --------------------------------------------------

    async def create_conversation(
        self, conversation_id: str, owner_client_id: str
    ) -> chat_db.ConversationRecord:
        return await self._db.run(
            chat_db.create_conversation, conversation_id, owner_client_id
        )

    async def get_conversation(
        self, conversation_id: str
    ) -> chat_db.ConversationRecord | None:
        return await self._db.run(chat_db.get_conversation, conversation_id)

    async def touch_conversation(
        self, conversation_id: str, last_turn_id: str | None
    ) -> None:
        await self._db.run(chat_db.touch_conversation, conversation_id, last_turn_id)

    async def list_conversations_for_owner(
        self,
        owner_client_id: str,
        *,
        archived: bool | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[chat_db.ConversationRecord]:
        return await self._db.run(
            chat_db.list_conversations_for_owner,
            owner_client_id,
            archived=archived,
            limit=limit,
            cursor=cursor,
        )

    # -- audit ---------------------------------------------------------------

    async def insert_audit_log(self, entry: audit_db.AuditLogEntry) -> None:
        await self._db.run(audit_db.insert_audit_log, entry)

    async def list_audit_logs(
        self,
        *,
        client_id: str | None = None,
        repository: str | None = None,
        limit: int = 100,
    ):
        return await self._db.run(
            audit_db.list_audit_logs, client_id=client_id, repository=repository, limit=limit
        )
