from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from .crypto import DEFAULT_ALGORITHM_SUITE, DEFAULT_PROTOCOL_VERSION, public_key_id
from .encoding import b64decode


DEFAULT_MAX_SKEW_MS = 30_000


@dataclass(frozen=True)
class SecureTransportSettings:
    enabled: bool
    protocol_version: str
    algorithm_suite: str
    identity: str
    key_id: str | None
    private_key: bytes | None
    trusted_public_keys: dict[str, bytes]
    max_skew_ms: int

    def trusted_public_key(self, key_id: str) -> bytes:
        """Return a trusted peer public key by key id or fail closed."""

        try:
            return self.trusted_public_keys[key_id]
        except KeyError as exc:
            raise ValueError(f"unknown trusted public key id: {key_id}") from exc


def load_secure_transport_settings(
    *,
    default_identity: str,
    env: Mapping[str, str] | None = None,
) -> SecureTransportSettings:
    """Load secure transport settings from environment variables."""

    source = os.environ if env is None else env
    settings = SecureTransportSettings(
        enabled=_parse_bool(source.get("SECURE_MODE", "false")),
        protocol_version=source.get("SICC_PROTOCOL_VERSION", DEFAULT_PROTOCOL_VERSION),
        algorithm_suite=source.get("SICC_ALGORITHM_SUITE", DEFAULT_ALGORITHM_SUITE),
        identity=source.get("SICC_SERVICE_IDENTITY", default_identity),
        key_id=source.get("SICC_SERVICE_KEY_ID") or None,
        private_key=_optional_key(source.get("SICC_SERVICE_PRIVATE_KEY_B64"), "private"),
        trusted_public_keys=_trusted_public_keys(
            source.get("SICC_TRUSTED_PUBLIC_KEYS_JSON", "{}")
        ),
        max_skew_ms=int(source.get("SICC_MAX_SKEW_MS", str(DEFAULT_MAX_SKEW_MS))),
    )

    if settings.enabled:
        _validate_enabled_settings(settings)

    return settings


def _validate_enabled_settings(settings: SecureTransportSettings) -> None:
    if not settings.identity:
        raise ValueError("SICC_SERVICE_IDENTITY is required when SECURE_MODE=true")
    if settings.protocol_version != DEFAULT_PROTOCOL_VERSION:
        raise ValueError(f"unsupported SICC_PROTOCOL_VERSION: {settings.protocol_version}")
    if settings.algorithm_suite != DEFAULT_ALGORITHM_SUITE:
        raise ValueError(f"unsupported SICC_ALGORITHM_SUITE: {settings.algorithm_suite}")
    if settings.private_key is None:
        raise ValueError("SICC_SERVICE_PRIVATE_KEY_B64 is required when SECURE_MODE=true")
    if settings.key_id is None:
        raise ValueError("SICC_SERVICE_KEY_ID is required when SECURE_MODE=true")
    if settings.max_skew_ms < 1:
        raise ValueError("SICC_MAX_SKEW_MS must be positive")


def _trusted_public_keys(raw_json: str) -> dict[str, bytes]:
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("SICC_TRUSTED_PUBLIC_KEYS_JSON must be valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("SICC_TRUSTED_PUBLIC_KEYS_JSON must be a JSON object")

    trusted: dict[str, bytes] = {}
    for key_id, encoded_key in raw.items():
        if not isinstance(key_id, str) or not isinstance(encoded_key, str):
            raise ValueError("trusted public key ids and values must be strings")
        key = _required_key(encoded_key, "public")
        if public_key_id(key) != key_id:
            raise ValueError(f"trusted public key id does not match key bytes: {key_id}")
        trusted[key_id] = key
    return trusted


def _optional_key(value: str | None, kind: str) -> bytes | None:
    if value is None or value == "":
        return None
    return _required_key(value, kind)


def _required_key(value: str, kind: str) -> bytes:
    try:
        key = b64decode(value)
    except Exception as exc:
        raise ValueError(f"{kind} key must be base64 encoded raw bytes") from exc
    if len(key) != 32:
        raise ValueError(f"{kind} key must decode to 32 bytes")
    return key


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("SECURE_MODE must be a boolean")
