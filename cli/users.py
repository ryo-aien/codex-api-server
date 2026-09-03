from __future__ import annotations

import argparse
import sys

from app.db import audit as audit_db
from app.db import clients as clients_db
from cli._db import open_db


def cmd_create(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = clients_db.create_client(conn, args.client_id, args.display_name, args.role)
    except clients_db.DuplicateClientError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (clients_db.InvalidClientIdError, clients_db.InvalidRoleError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Client created")
    print()
    print(f"client_id:    {record.client_id}")
    print(f"display_name: {record.display_name or ''}")
    print(f"role:         {record.role}")
    print(f"enabled:      {record.enabled}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    conn = open_db()
    records = clients_db.list_clients(conn)

    if not records:
        print("No clients found")
        return 0

    print(f"{'client_id':<24} {'role':<8} {'enabled':<8} {'display_name':<24} created_at")
    for r in records:
        print(
            f"{r.client_id:<24} {r.role:<8} {str(r.enabled):<8} "
            f"{(r.display_name or ''):<24} {r.created_at}"
        )
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = clients_db.set_enabled(conn, args.client_id, False)
    except clients_db.ClientNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Client '{record.client_id}' disabled")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    conn = open_db()
    try:
        record = clients_db.set_enabled(conn, args.client_id, True)
    except clients_db.ClientNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Client '{record.client_id}' enabled")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    conn = open_db()
    rows = audit_db.list_audit_logs(conn, client_id=args.client_id, limit=args.limit)

    if not rows:
        print("No audit log entries found")
        return 0

    for row in rows:
        print(
            f"{row['timestamp']}  action={row['action']:<20} "
            f"status={row['status_code']}  path={row['path']}  "
            f"thread_id={row['thread_id']}  request_id={row['request_id']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.users")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_create = subparsers.add_parser("create", help="Create a new client")
    p_create.add_argument("--client-id", required=True)
    p_create.add_argument("--display-name", default=None)
    p_create.add_argument("--role", default="user", choices=["user", "admin"])
    p_create.set_defaults(func=cmd_create)

    p_list = subparsers.add_parser("list", help="List all clients")
    p_list.set_defaults(func=cmd_list)

    p_disable = subparsers.add_parser("disable", help="Disable a client")
    p_disable.add_argument("client_id")
    p_disable.set_defaults(func=cmd_disable)

    p_enable = subparsers.add_parser("enable", help="Enable a client")
    p_enable.add_argument("client_id")
    p_enable.set_defaults(func=cmd_enable)

    p_audit = subparsers.add_parser("audit", help="Show audit log entries for a client")
    p_audit.add_argument("client_id")
    p_audit.add_argument("--limit", type=int, default=100)
    p_audit.set_defaults(func=cmd_audit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
