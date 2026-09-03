from __future__ import annotations

import argparse
import asyncio
import sys

from openai_codex import AsyncCodex

from app.codex.auth import build_codex_config, get_account_status
from app.config import get_settings


async def _login() -> int:
    settings = get_settings()
    config = build_codex_config(settings)

    async with AsyncCodex(config) as codex:
        if settings.codex_auth_mode == "api_key":
            if not settings.openai_api_key:
                print("Error: CODEX_AUTH_MODE=api_key requires OPENAI_API_KEY", file=sys.stderr)
                return 1
            await codex.login_api_key(settings.openai_api_key)
            print("Logged in with OPENAI_API_KEY")
            return 0

        handle = await codex.login_chatgpt_device_code()
        print("Verification URL:")
        print(handle.verification_url)
        print()
        print("Code:")
        print(handle.user_code)
        print()
        print("Waiting for login to complete...")

        result = await handle.wait()
        if not result.success:
            print(f"Login failed: {result.error}", file=sys.stderr)
            return 1

        print("Login successful.")
        return 0


async def _status() -> int:
    settings = get_settings()
    config = build_codex_config(settings)

    async with AsyncCodex(config) as codex:
        status_info = await get_account_status(codex)

    print(f"authenticated: {status_info['authenticated']}")
    print(f"auth_mode: {status_info['auth_mode'] or 'none'}")
    return 0


def cmd_login(_args: argparse.Namespace) -> int:
    return asyncio.run(_login())


def cmd_status(_args: argparse.Namespace) -> int:
    return asyncio.run(_status())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.codex_auth")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_login = subparsers.add_parser("login", help="Authenticate the backend Codex runtime")
    p_login.set_defaults(func=cmd_login)

    p_status = subparsers.add_parser("status", help="Show backend Codex authentication status")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
