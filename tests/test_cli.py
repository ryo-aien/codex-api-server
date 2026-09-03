from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    db_path = tmp_path / "cli-test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("API_KEY_PEPPER", "cli-test-pepper")
    monkeypatch.setenv("CODEX_AUTH_MODE", "chatgpt")

    import app.config as config_module

    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


def test_api_key_create_shows_raw_key_once(cli_env, capsys):
    from cli import users, api_keys

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    exit_code = api_keys.main(["create", "alice"])
    assert exit_code == 0

    output = capsys.readouterr().out
    assert "cax_" in output
    assert "will only be shown once" in output


def test_api_key_list_never_shows_raw_key(cli_env, capsys):
    from cli import users, api_keys

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    api_keys.main(["create", "alice"])
    created_output = capsys.readouterr().out
    raw_key = [line for line in created_output.splitlines() if line.startswith("cax_")][0]

    api_keys.main(["list", "alice"])
    list_output = capsys.readouterr().out

    assert raw_key not in list_output
    assert "cax_" not in list_output
    assert "key_id" in list_output or "cak_" in list_output


def test_user_create_and_list(cli_env, capsys):
    from cli import users

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    exit_code = users.main(["list"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "alice" in output


def test_user_disable_enable(cli_env, capsys):
    from cli import users

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    users.main(["disable", "alice"])
    disable_output = capsys.readouterr().out
    assert "disabled" in disable_output

    users.main(["enable", "alice"])
    enable_output = capsys.readouterr().out
    assert "enabled" in enable_output


def test_api_key_revoke(cli_env, capsys):
    from cli import users, api_keys

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    api_keys.main(["create", "alice"])
    created_output = capsys.readouterr().out
    key_id_line = [line for line in created_output.splitlines() if line.startswith("key_id:")][0]
    key_id = key_id_line.split(":", 1)[1].strip()

    exit_code = api_keys.main(["revoke", key_id])
    assert exit_code == 0
    assert "revoked" in capsys.readouterr().out


def test_duplicate_client_id_cli_error(cli_env, capsys):
    from cli import users

    users.main(["create", "--client-id", "alice", "--display-name", "Alice"])
    capsys.readouterr()

    exit_code = users.main(["create", "--client-id", "alice", "--display-name", "Alice 2"])
    assert exit_code == 1
