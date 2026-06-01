from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any


def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(value + padding)


def create_enrollment_token(
    secret: str, agent_name: str, expires_at: int | None = None
) -> str:
    payload: dict[str, Any] = {"name": agent_name}
    if expires_at is not None:
        payload["exp"] = expires_at

    payload_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload_part = _b64url_encode(payload_bytes)
    signature = hmac.new(
        secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload_part}.{_b64url_encode(signature)}"


def verify_enrollment_token(secret: str, token: str, agent_name: str) -> bool:
    try:
        payload_part, signature_part = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        submitted_signature = _b64url_decode(signature_part)
        if not hmac.compare_digest(expected_signature, submitted_signature):
            return False

        payload = json.loads(_b64url_decode(payload_part))
    except Exception:
        return False

    if payload.get("name") != agent_name:
        return False

    expires_at = payload.get("exp")
    if expires_at is not None:
        if not isinstance(expires_at, int):
            return False
        if int(time.time()) > expires_at:
            return False

    return True
