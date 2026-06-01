from __future__ import annotations

import argparse
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server-iot"))

from app.enrollment import create_enrollment_token


def add_generate_secret_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        "secret",
        help="Generate a server enrollment secret for env/.env.server-iot.",
        description="Generate a server enrollment secret for env/.env.server-iot.",
    )


def add_generate_token_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "token",
        help="Generate a signed enrollment token for one agent.",
        description="Generate a signed enrollment token for one agent.",
    )
    parser.add_argument("agent_name", help="Agent name the token is valid for.")
    parser.add_argument(
        "--secret",
        required=True,
        help="Existing server enrollment secret. If omitted, a new one is generated.",
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        help="Optional token lifetime in seconds.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate server secrets and signed per-agent enrollment tokens."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_generate_secret_parser(subparsers)
    add_generate_token_parser(subparsers)
    args = parser.parse_args()

    if args.command == "secret":
        print(f"SICC_AGENT_ENROLLMENT_SECRET={secrets.token_urlsafe(32)}")
        return

    expires_at = None
    if args.ttl_seconds is not None:
        expires_at = int(time.time()) + args.ttl_seconds

    token = create_enrollment_token(args.secret, args.agent_name, expires_at=expires_at)
    print(f"AGENT_ENROLLMENT_TOKEN={token}")


if __name__ == "__main__":
    main()
