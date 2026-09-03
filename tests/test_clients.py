from __future__ import annotations

import pytest

from app.db import clients as clients_db


@pytest.mark.asyncio
async def test_create_client(repo):
    record = await repo.create_client("alice", "Alice")
    assert record.client_id == "alice"
    assert record.display_name == "Alice"
    assert record.role == "user"
    assert record.enabled is True


@pytest.mark.asyncio
async def test_duplicate_client_id_rejected(repo):
    await repo.create_client("alice", "Alice")
    with pytest.raises(clients_db.DuplicateClientError):
        await repo.create_client("alice", "Someone Else")


@pytest.mark.asyncio
async def test_disable_and_enable_client(repo):
    await repo.create_client("alice", "Alice")
    disabled = await repo.set_client_enabled("alice", False)
    assert disabled.enabled is False

    enabled = await repo.set_client_enabled("alice", True)
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_admin_and_user_roles(repo):
    admin = await repo.create_client("admin", "Administrator", role="admin")
    user = await repo.create_client("alice", "Alice", role="user")
    assert admin.role == "admin"
    assert user.role == "user"


def test_invalid_client_id_rejected():
    with pytest.raises(clients_db.InvalidClientIdError):
        clients_db.validate_client_id("has a space")
    with pytest.raises(clients_db.InvalidClientIdError):
        clients_db.validate_client_id("")
    with pytest.raises(clients_db.InvalidClientIdError):
        clients_db.validate_client_id("a" * 65)


@pytest.mark.asyncio
async def test_invalid_role_rejected(repo):
    with pytest.raises(clients_db.InvalidRoleError):
        await repo.create_client("alice", "Alice", role="superuser")
