from __future__ import annotations

import pytest

from app.db.connection import Database
from app.db.migrations import run_migrations
from app.dependencies import (
    InvalidRepositoryNameError,
    resolve_repository_path,
    validate_repository_name,
)
from app.errors import RepositoryNotFoundError
from app.repository import Repository


def test_valid_repository_name_accepted():
    validate_repository_name("project-a")
    validate_repository_name("project_a.v2")


@pytest.mark.parametrize(
    "name",
    ["../etc", "../../etc", "/etc", ".", "..", "~", "a/b", "a\\b"],
)
def test_invalid_repository_names_rejected(name):
    with pytest.raises(InvalidRepositoryNameError):
        validate_repository_name(name)


def test_resolve_repository_path_success(tmp_path):
    root = tmp_path / "workspaces"
    (root / "project-a").mkdir(parents=True)

    resolved = resolve_repository_path(str(root), "project-a")
    assert resolved == (root / "project-a").resolve()


@pytest.mark.parametrize(
    "name",
    ["../etc", "../../etc", "/etc", ".", "..", "~"],
)
def test_resolve_repository_path_rejects_traversal(tmp_path, name):
    root = tmp_path / "workspaces"
    root.mkdir()

    with pytest.raises(RepositoryNotFoundError):
        resolve_repository_path(str(root), name)


def test_resolve_repository_path_rejects_nonexistent(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()

    with pytest.raises(RepositoryNotFoundError):
        resolve_repository_path(str(root), "does-not-exist")


def test_resolve_repository_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    escape_link = root / "escape"
    escape_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RepositoryNotFoundError):
        resolve_repository_path(str(root), "escape")


@pytest.mark.asyncio
async def test_data_persists_across_db_reopen(tmp_path):
    db_path = str(tmp_path / "persist-test.db")

    db1 = Database(db_path)
    db1.connect_sync()
    await db1.run(run_migrations)
    repo1 = Repository(db1)

    client = await repo1.create_client("alice", "Alice")
    from app.security.api_keys import generate_key_id, generate_raw_api_key, hash_api_key

    key_id = generate_key_id()
    key_hash = hash_api_key(generate_raw_api_key(), "pepper")
    await repo1.create_api_key(client.id, key_id, key_hash)
    await repo1.create_thread("thr_persist_1", "alice", "project-a")
    db1.close()

    db2 = Database(db_path)
    db2.connect_sync()
    await db2.run(run_migrations)
    repo2 = Repository(db2)

    reloaded_client = await repo2.get_client("alice")
    assert reloaded_client is not None
    assert reloaded_client.client_id == "alice"

    reloaded_keys = await repo2.list_api_keys_by_client(client.id)
    assert len(reloaded_keys) == 1
    assert reloaded_keys[0].key_id == key_id

    reloaded_thread = await repo2.get_thread("thr_persist_1")
    assert reloaded_thread is not None
    assert reloaded_thread.owner_client_id == "alice"
    db2.close()
