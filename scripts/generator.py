from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security import generate_ed25519_keypair, public_key_id
from security.encoding import b64encode


def cmd_secret() -> None:
    print(f"SICC_AGENT_ENROLLMENT_SECRET={secrets.token_urlsafe(32)}")


def cmd_keypair() -> None:
    keypair = generate_ed25519_keypair()
    key_id = public_key_id(keypair.public_key)
    print(f"SICC_SERVICE_KEY_ID={key_id}")
    print(f"SICC_SERVICE_PRIVATE_KEY_B64={b64encode(keypair.private_key)}")
    print(f"SICC_SERVICE_PUBLIC_KEY_B64={b64encode(keypair.public_key)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SICC secrets and keypairs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("secret", help="Generate a random enrollment secret token")
    subparsers.add_parser("keypair", help="Generate an Ed25519 keypair for the service")

    args = parser.parse_args()

    if args.command == "secret":
        cmd_secret()
    elif args.command == "keypair":
        cmd_keypair()


if __name__ == "__main__":
    main()
