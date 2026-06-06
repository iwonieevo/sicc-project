from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import b64decode
from dataclasses import dataclass

from valkey import Valkey, ValkeyError

TOKEN_ISSUER = "agents.py"

_client: Valkey | None = None


def _get_client() -> Valkey:
    global _client
    if _client is None:
        url = os.getenv("SICC_VALKEY_URL")
        if not url:
            raise RuntimeError("SICC_VALKEY_URL is required for secure enrollment")
        _client = Valkey.from_url(url, decode_responses=True)
    return _client


@dataclass(frozen=True)
class EnrollmentTokenClaims:
    agent_id: str
    jti: str
    issued_at: int
    expires_at: int


def verify_enrollment_token(
    secret: str, token: str, agent_name: str
) -> EnrollmentTokenClaims | None:
    try:
        payload_part, signature_part = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        submitted_signature = b64decode(signature_part)
        if not hmac.compare_digest(expected_signature, submitted_signature):
            return None

        payload = json.loads(b64decode(payload_part))
    except Exception:
        return None

    if payload.get("v") != 1:
        return None
    if payload.get("iss") != TOKEN_ISSUER:
        return None
    if payload.get("agent_id", payload.get("sub")) != agent_name:
        return None

    jti = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if not isinstance(jti, str) or not jti:
        return None
    if not isinstance(issued_at, int) or isinstance(issued_at, bool):
        return None
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        return None

    now = int(time.time())
    if expires_at <= issued_at:
        return None
    if now > expires_at:
        return None

    return EnrollmentTokenClaims(
        agent_id=agent_name,
        jti=jti,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def consume_enrollment_jti(claims: EnrollmentTokenClaims) -> bool:
    ttl_seconds = claims.expires_at - int(time.time())
    if ttl_seconds <= 0:
        return False

    key = f"agents:used-jti:{claims.jti}"
    try:
        return bool(
            _get_client().set(
                key,
                claims.agent_id,
                nx=True,
                ex=ttl_seconds,
            )
        )
    except ValkeyError as exc:
        raise RuntimeError("Valkey enrollment state is unavailable") from exc
