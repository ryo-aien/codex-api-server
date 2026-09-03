from __future__ import annotations

import pytest

from tests.conftest import create_client_with_key


@pytest.mark.asyncio
async def test_authenticated_request_writes_audit_row(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, key_id = await create_client_with_key(repo, test_settings, "alice")

    created = await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}", "X-Request-ID": "req-abc-123"},
        json={"repository": "project-a", "prompt": "investigate this"},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread_id"]

    rows = await repo.list_audit_logs(client_id="alice", limit=10)
    assert len(rows) >= 1
    row = rows[0]
    assert row["client_id"] == "alice"
    assert row["key_id"] == key_id
    assert row["request_id"] == "req-abc-123"
    assert row["repository"] == "project-a"
    assert row["thread_id"] == thread_id
    assert row["status_code"] == 200


@pytest.mark.asyncio
async def test_audit_log_records_error_code_for_api_errors(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    response = await http_client.post(
        "/v1/threads/thr_does_not_exist/messages",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"prompt": "hello"},
    )
    assert response.status_code == 404

    rows = await repo.list_audit_logs(client_id="alice", limit=10)
    assert rows[0]["error_code"] == "thread_not_found"
    assert rows[0]["status_code"] == 404


@pytest.mark.asyncio
async def test_authentication_failure_logged_without_client_id(app_client, repo):
    http_client, _app = app_client

    response = await http_client.get(
        "/v1/me", headers={"Authorization": "Bearer cax_bad_key"}
    )
    assert response.status_code == 401

    rows = await repo.list_audit_logs(limit=10)
    failure_rows = [r for r in rows if r["action"] == "authentication_failure"]
    assert len(failure_rows) >= 1
    row = failure_rows[0]
    assert row["client_id"] is None
    assert row["key_id"] is None
    assert row["status_code"] == 401
    assert row["path"] == "/v1/me"


@pytest.mark.asyncio
async def test_audit_log_never_contains_raw_api_key(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": "a secret-ish prompt body"},
    )

    conn = repo._db.raw
    rows = conn.execute("SELECT * FROM audit_logs").fetchall()
    for row in rows:
        serialized = " ".join(str(row[k]) for k in row.keys())
        assert raw_key not in serialized
        assert "a secret-ish prompt body" not in serialized
        assert "Bearer" not in serialized


@pytest.mark.asyncio
async def test_audit_log_records_prompt_chars_not_full_prompt(app_client, repo, test_settings):
    http_client, _app = app_client
    _c, raw_key, _kid = await create_client_with_key(repo, test_settings, "alice")

    prompt = "investigate the login bug in detail please"
    await http_client.post(
        "/v1/threads",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"repository": "project-a", "prompt": prompt},
    )

    rows = await repo.list_audit_logs(client_id="alice", limit=10)
    row = rows[0]
    assert row["prompt_chars"] == len(prompt)
