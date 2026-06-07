import hashlib
import hmac
import json
import sys
import time
from base64 import b64encode
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server-iot"))

from app import enrollment  # noqa: E402
from app.enrollment import EnrollmentTokenClaims, verify_enrollment_token  # noqa: E402


class FakeValkey:
    def __init__(self):
        self.values = {}

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = {"value": value, "ex": ex}
        return True


def signed_token(secret: str, payload: dict) -> str:
    payload_part = b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{b64encode(signature).decode('ascii')}"


def token_payload(**overrides):
    now = int(time.time())
    payload = {
        "v": 1,
        "iss": "agents.py",
        "agent_id": "agent-alpha",
        "jti": "token-id",
        "iat": now,
        "exp": now + 60,
    }
    payload.update(overrides)
    return payload


def test_verify_enrollment_token_accepts_valid_payload():
    claims = verify_enrollment_token(
        "secret",
        signed_token("secret", token_payload()),
        "agent-alpha",
    )

    assert claims == EnrollmentTokenClaims(
        agent_id="agent-alpha",
        jti="token-id",
        issued_at=claims.issued_at,
        expires_at=claims.expires_at,
    )


def test_verify_enrollment_token_rejects_expired_token():
    now = int(time.time())
    token = signed_token(
        "secret",
        token_payload(iat=now - 120, exp=now - 60),
    )

    assert verify_enrollment_token("secret", token, "agent-alpha") is None


def test_verify_enrollment_token_rejects_wrong_secret():
    token = signed_token("secret", token_payload())

    assert verify_enrollment_token("wrong-secret", token, "agent-alpha") is None


def test_verify_enrollment_token_rejects_wrong_agent():
    token = signed_token("secret", token_payload(agent_id="agent-alpha"))

    assert verify_enrollment_token("secret", token, "agent-beta") is None


def test_consume_enrollment_jti_rejects_duplicate(monkeypatch):
    client = FakeValkey()
    monkeypatch.setattr(enrollment, "_client", client)
    claims = EnrollmentTokenClaims(
        agent_id="agent-alpha",
        jti="duplicate-token-id",
        issued_at=int(time.time()),
        expires_at=int(time.time()) + 60,
    )

    assert enrollment.consume_enrollment_jti(claims) is True
    assert enrollment.consume_enrollment_jti(claims) is False


def test_consume_enrollment_jti_rejects_expired_claims(monkeypatch):
    client = FakeValkey()
    monkeypatch.setattr(enrollment, "_client", client)
    claims = EnrollmentTokenClaims(
        agent_id="agent-alpha",
        jti="expired-token-id",
        issued_at=int(time.time()) - 120,
        expires_at=int(time.time()) - 60,
    )

    assert enrollment.consume_enrollment_jti(claims) is False
