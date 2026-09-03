from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.db import api_keys as api_keys_db
from app.db import clients as clients_db
from app.security.api_keys import generate_key_id, generate_raw_api_key, hash_api_key
from cli._db import open_db


def cmd_create(args: argparse.Namespace) -> int:
    conn = open_db()
    client = clients_db.get_client(conn, args.client_id)
    if client is None:
        print(f"Error: client_id '{args.client_id}' not found", file=sys.stderr)
        return 1

    settings = get_settings()
    raw_key = generate_raw_api_key()
    key_id = generate_key_id()
    key_hash = hash_api_key(raw_key, settings.api_key_pepper)

    api_keys_db.create_api_key(
        conn, client.id, key_id, key_hash, expires_in_days=args.expires_in_days
    )

    print("API key created")
    print()
    print(f"client_id: {client.client_id}")
    print(f"key_id: {key_id}")
    print()
    print("API key:")
    print(raw_key)
    print()
    print("IMPORTANT:")
    print("This key will only be shown once.")
    print("Store it securely.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = open_db()
    client = clients_db.get_client(conn, args.client_id)
    if client is None:
        print(f"Error: client_id '{args.client_id}' not found", file=sys.stderr)
        return 1

    records = api_keys_db.list_by_client(conn, client.id)
    if not records:
        print("No API keys found")
        return 0

    print(f"{'key_id':<16} {'enabled':<8} {'created_at':<28} {'last_used_at':<28} {'expires_at':<28} revoked_at")
    for r in records:
        print(
            f"{r.key_id:<16} {str(r.enabled):<8} {r.created_at:<28} "
            f"{(r.last_used_at or ''):<28} {(r.expires_at or ''):<28} {r.revoked_at or ''}"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = api_keys_db.revoke(conn, args.key_id)
    except api_keys_db.ApiKeyNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"API key '{record.key_id}' revoked")
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = api_keys_db.set_enabled(conn, args.key_id, False)
    except api_keys_db.ApiKeyNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"API key '{record.key_id}' disabled")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = api_keys_db.set_enabled(conn, args.key_id, True)
    except api_keys_db.ApiKeyNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"API key '{record.key_id}' enabled")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    """Create a new key for the client, then revoke the old one.

    This performs steps 1 and 3 of the rotation workflow described in the
    README; step 2 (switching the client over) happens outside this tool.
    """
    conn = open_db()
    client = clients_db.get_client(conn, args.client_id)
    if client is None:
        print(f"Error: client_id '{args.client_id}' not found", file=sys.stderr)
        return 1

    old_key = api_keys_db.get_by_key_id(conn, args.old_key_id)
    if old_key is None or old_key.client_db_id != client.id:
        print(f"Error: key_id '{args.old_key_id}' not found for client '{args.client_id}'", file=sys.stderr)
        return 1

    settings = get_settings()
    raw_key = generate_raw_api_key()
    key_id = generate_key_id()
    key_hash = hash_api_key(raw_key, settings.api_key_pepper)
    api_keys_db.create_api_key(
        conn, client.id, key_id, key_hash, expires_in_days=args.expires_in_days
    )
    api_keys_db.revoke(conn, args.old_key_id)

    print("API key rotated")
    print()
    print(f"client_id: {client.client_id}")
    print(f"new key_id: {key_id}")
    print(f"revoked key_id: {args.old_key_id}")
    print()
    print("New API key:")
    print(raw_key)
    print()
    print("IMPORTANT:")
    print("This key will only be shown once.")
    print("Store it securely.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.api_keys")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_create = subparsers.add_parser("create", help="Create a new API key for a client")
    p_create.add_argument("client_id")
    p_create.add_argument("--expires-in-days", type=int, default=None)
    p_create.set_defaults(func=cmd_create)

    p_list = subparsers.add_parser("list", help="List API keys for a client")
    p_list.add_argument("client_id")
    p_list.set_defaults(func=cmd_list)

    p_revoke = subparsers.add_parser("revoke", help="Revoke an API key")
    p_revoke.add_argument("key_id")
    p_revoke.set_defaults(func=cmd_revoke)

    p_disable = subparsers.add_parser("disable", help="Disable an API key")
    p_disable.add_argument("key_id")
    p_disable.set_defaults(func=cmd_disable)

    p_enable = subparsers.add_parser("enable", help="Enable an API key")
    p_enable.add_argument("key_id")
    p_enable.set_defaults(func=cmd_enable)

    p_rotate = subparsers.add_parser(
        "rotate", help="Create a new key and revoke an old one for a client"
    )
    p_rotate.add_argument("client_id")
    p_rotate.add_argument("--old-key-id", required=True)
    p_rotate.add_argument("--expires-in-days", type=int, default=None)
    p_rotate.set_defaults(func=cmd_rotate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
