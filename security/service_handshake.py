from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .crypto import (
    DerivedKeys,
    HandshakeTranscript,
    KeyPair,
    derive_session_keys,
    generate_x25519_keypair,
    sign_transcript,
    verify_transcript_signature,
)
from .errors import StaleMessageError
from .settings import SecureTransportSettings

ROLE_BACKEND_IOT = "backend-iot"


@dataclass(frozen=True)
class HandshakeStart:
    """Client's first handshake message before a full transcript can be built."""

    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    client_ephemeral_pubkey: bytes
    timestamp_ms: int


@dataclass(frozen=True)
class ServerHandshake:
    """Server-side handshake result with the signed transcript and session keys."""

    transcript: HandshakeTranscript
    server_ephemeral: KeyPair
    server_signature: bytes
    keys: DerivedKeys


@dataclass(frozen=True)
class ClientHandshake:
    """Client-side handshake result after verifying the server signature."""

    transcript: HandshakeTranscript
    client_ephemeral: KeyPair
    client_signature: bytes
    keys: DerivedKeys


def new_session_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    return int(time.time() * 1000)


def create_handshake_start(
    settings: SecureTransportSettings,
    *,
    role: str,
    server_identity: str,
    server_key_id: str,
    timestamp_ms: int | None = None,
) -> tuple[HandshakeStart, KeyPair]:
    """Create the client's initial handshake message and X25519 ephemeral keypair."""

    assert settings.enabled, "secure transport is disabled"

    if settings.key_id is None:
        raise ValueError("local service key id is not configured")
    settings.trusted_public_key(server_key_id)

    client_ephemeral = generate_x25519_keypair()
    start = HandshakeStart(
        role=role,
        session_id=new_session_id(),
        client_identity=settings.identity,
        server_identity=server_identity,
        client_key_id=settings.key_id,
        server_key_id=server_key_id,
        client_ephemeral_pubkey=client_ephemeral.public_key,
        timestamp_ms=now_ms() if timestamp_ms is None else timestamp_ms,
    )
    return start, client_ephemeral


def create_server_handshake(
    settings: SecureTransportSettings,
    start: HandshakeStart,
    *,
    expected_role: str,
    expected_client_identity: str,
    expected_server_identity: str,
    timestamp_ms: int | None = None,
) -> ServerHandshake:
    """Validate a client start message, sign the transcript, and derive server keys."""

    assert settings.enabled, "secure transport is disabled"

    _validate_start(
        settings,
        start,
        expected_role=expected_role,
        expected_client_identity=expected_client_identity,
        expected_server_identity=expected_server_identity,
        timestamp_ms=timestamp_ms,
    )

    server_ephemeral = generate_x25519_keypair()
    transcript = HandshakeTranscript(
        protocol_version=settings.protocol_version,
        role=start.role,
        algorithm_suite=settings.algorithm_suite,
        session_id=start.session_id,
        client_identity=start.client_identity,
        server_identity=start.server_identity,
        client_key_id=start.client_key_id,
        server_key_id=start.server_key_id,
        server_ephemeral_pubkey=server_ephemeral.public_key,
        client_ephemeral_pubkey=start.client_ephemeral_pubkey,
        timestamp_ms=start.timestamp_ms,
    )

    assert settings.private_key is not None
    signature = sign_transcript(settings.private_key, transcript)
    keys = derive_session_keys(
        server_ephemeral.private_key,
        start.client_ephemeral_pubkey,
        transcript,
    )
    return ServerHandshake(
        transcript=transcript,
        server_ephemeral=server_ephemeral,
        server_signature=signature,
        keys=keys,
    )


def complete_client_handshake(
    settings: SecureTransportSettings,
    start: HandshakeStart,
    client_ephemeral: KeyPair,
    *,
    server_ephemeral_pubkey: bytes,
    server_signature: bytes,
    timestamp_ms: int | None = None,
) -> ClientHandshake:
    """Verify the server's signed transcript, then sign it as the client."""

    assert settings.enabled, "secure transport is disabled"

    if start.client_identity != settings.identity:
        raise ValueError("unexpected client identity")
    if start.client_key_id != settings.key_id:
        raise ValueError("unexpected client key id")
    settings.trusted_public_key(start.server_key_id)
    _validate_timestamp(start.timestamp_ms, settings.max_skew_ms, timestamp_ms)

    transcript = HandshakeTranscript(
        protocol_version=settings.protocol_version,
        role=start.role,
        algorithm_suite=settings.algorithm_suite,
        session_id=start.session_id,
        client_identity=start.client_identity,
        server_identity=start.server_identity,
        client_key_id=start.client_key_id,
        server_key_id=start.server_key_id,
        server_ephemeral_pubkey=server_ephemeral_pubkey,
        client_ephemeral_pubkey=start.client_ephemeral_pubkey,
        timestamp_ms=start.timestamp_ms,
    )
    server_public_key = settings.trusted_public_key(start.server_key_id)
    verify_transcript_signature(server_public_key, transcript, server_signature)

    assert settings.private_key is not None
    client_signature = sign_transcript(settings.private_key, transcript)
    keys = derive_session_keys(
        client_ephemeral.private_key,
        server_ephemeral_pubkey,
        transcript,
    )
    return ClientHandshake(
        transcript=transcript,
        client_ephemeral=client_ephemeral,
        client_signature=client_signature,
        keys=keys,
    )


def verify_client_handshake_signature(
    settings: SecureTransportSettings,
    transcript: HandshakeTranscript,
    client_signature: bytes,
) -> None:
    """Verify the client's final signature over an already-built transcript."""

    assert settings.enabled, "secure transport is disabled"

    client_public_key = settings.trusted_public_key(transcript.client_key_id)
    verify_transcript_signature(client_public_key, transcript, client_signature)


def _validate_start(
    settings: SecureTransportSettings,
    start: HandshakeStart,
    *,
    expected_role: str,
    expected_client_identity: str,
    expected_server_identity: str,
    timestamp_ms: int | None,
) -> None:
    if start.role != expected_role:
        raise ValueError("unexpected handshake role")
    if start.client_identity != expected_client_identity:
        raise ValueError("unexpected client identity")
    if start.server_identity != expected_server_identity:
        raise ValueError("unexpected server identity")
    if start.server_key_id != settings.key_id:
        raise ValueError("unexpected server key id")
    settings.trusted_public_key(start.client_key_id)
    _validate_timestamp(start.timestamp_ms, settings.max_skew_ms, timestamp_ms)


def _validate_timestamp(value: int, max_skew_ms: int, timestamp_ms: int | None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("handshake timestamp must be an integer")
    current = now_ms() if timestamp_ms is None else timestamp_ms
    if abs(current - value) > max_skew_ms:
        raise StaleMessageError("handshake timestamp is outside allowed skew")
