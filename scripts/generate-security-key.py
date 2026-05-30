from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security import generate_ed25519_keypair, public_key_id
from security.encoding import b64encode


def main() -> None:
    keypair = generate_ed25519_keypair()
    key_id = public_key_id(keypair.public_key)
    print(f"SICC_SERVICE_KEY_ID={key_id}")
    print(f"SICC_SERVICE_PRIVATE_KEY_B64={b64encode(keypair.private_key)}")
    print(f"SICC_SERVICE_PUBLIC_KEY_B64={b64encode(keypair.public_key)}")


if __name__ == "__main__":
    main()
