from __future__ import annotations

import argparse
import sys

from app.db import audit as audit_db
from cli._db import open_db


def cmd_list(args: argparse.Namespace) -> int:
    conn = open_db()
    rows = audit_db.list_audit_logs(
        conn, client_id=args.client_id, repository=args.repository, limit=args.limit
    )

    if not rows:
        print("No audit log entries found")
        return 0

    for row in rows:
        print(
            f"{row['timestamp']}  client_id={row['client_id']}  key_id={row['key_id']}  "
            f"action={row['action']}  method={row['method']}  path={row['path']}  "
            f"repository={row['repository']}  thread_id={row['thread_id']}  "
            f"status={row['status_code']}  duration_ms={row['duration_ms']}  "
            f"remote_ip={row['remote_ip']}  prompt_chars={row['prompt_chars']}  "
            f"result_status={row['result_status']}  error_code={row['error_code']}  "
            f"request_id={row['request_id']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.audit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="List audit log entries")
    p_list.add_argument("--client-id", default=None)
    p_list.add_argument("--repository", default=None)
    p_list.add_argument("--limit", type=int, default=100)
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
