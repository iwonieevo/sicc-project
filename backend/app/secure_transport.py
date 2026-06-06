import logging
import os
from threading import RLock
from typing import Any

import httpx

from security import (
    ROLE_BACKEND_IOT,
    CryptoError,
    Direction,
    HandshakeStart,
    SecureEnvelope,
    SecureSession,
    SecureSessionStore,
    complete_client_handshake,
    create_handshake_start,
    decode_handshake_field,
    decrypt_envelope,
    encrypt_envelope,
    load_secure_transport_settings,
)
from security.encoding import b64encode

IOT_SERVER_URL = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
IOT_SERVER_IDENTITY = os.getenv("SICC_IOT_SERVER_IDENTITY")
IOT_SERVER_KEY_ID = os.getenv("SICC_IOT_SERVER_KEY_ID")

LOGGER = logging.getLogger(__name__)
settings = load_secure_transport_settings(default_identity="backend")
session_store = SecureSessionStore()
client = httpx.Client(timeout=10.0)
session_creation_lock = RLock()


def select_iot_server_key_id() -> str:
    """Return the configured IoT server key id used for backend-IoT handshakes."""

    if IOT_SERVER_KEY_ID:
        return IOT_SERVER_KEY_ID
    raise ValueError("SICC_IOT_SERVER_KEY_ID is required when SECURE_MODE=true")


def select_iot_server_identity() -> str:
    """Return the configured IoT server identity used for backend-IoT handshakes."""

    if IOT_SERVER_IDENTITY:
        return IOT_SERVER_IDENTITY
    raise ValueError("SICC_IOT_SERVER_IDENTITY is required when SECURE_MODE=true")


def initiate_backend_iot_handshake(client: httpx.Client | None = None) -> SecureSession:
    """Perform the full backend-to-IoT mutual handshake and store the session."""

    server_key_id = select_iot_server_key_id()
    server_identity = select_iot_server_identity()
    start, client_ephemeral = create_handshake_start(
        settings,
        role=ROLE_BACKEND_IOT,
        server_identity=server_identity,
        server_key_id=server_key_id,
    )
    owns_client = client is None
    http_client = httpx.Client(timeout=10.0) if client is None else client

    try:
        start_response = http_client.post(
            _iot_url("/secure/backend-iot/handshake/start"),
            json=_start_to_payload(start),
        )
        start_response.raise_for_status()
        data = start_response.json()
        _validate_start_response(start, data)

        server_signature = decode_handshake_field(data["server_signature"])
        server_ephemeral_pubkey = decode_handshake_field(
            data["server_ephemeral_pubkey"]
        )
        client_handshake = complete_client_handshake(
            settings,
            start,
            client_ephemeral,
            server_ephemeral_pubkey=server_ephemeral_pubkey,
            server_signature=server_signature,
        )

        finish_response = http_client.post(
            _iot_url("/secure/backend-iot/handshake/finish"),
            json={
                "session_id": client_handshake.transcript.session_id,
                "client_signature": b64encode(client_handshake.client_signature),
            },
        )
        finish_response.raise_for_status()
    except httpx.HTTPError as exc:
        LOGGER.warning("Backend-IoT secure handshake request failed: %s", exc)
        raise
    finally:
        if owns_client:
            http_client.close()

    session = SecureSession(
        transcript=client_handshake.transcript,
        keys=client_handshake.keys,
    )
    session_store.put(session)
    LOGGER.info(
        "Established backend-IoT secure session %s",
        session.transcript.session_id,
    )
    return session


def get_or_create_backend_iot_session() -> SecureSession:
    """Return the active backend-IoT session, creating exactly one under concurrency."""

    session = session_store.first()
    if session is not None:
        return session
    with session_creation_lock:
        session = session_store.first()
        if session is not None:
            return session
        return initiate_backend_iot_handshake(client)


def forward_secure_backend_iot_request(
    *,
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Forward one IoT request through secure transport, refreshing stale sessions once."""

    try:
        return _forward_secure_backend_iot_request(
            method=method,
            path=path,
            json_data=json_data,
            params=params,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            _discard_backend_iot_sessions()
            raise
        LOGGER.info("Backend-IoT secure session missing remotely; handshaking again")
        _discard_backend_iot_sessions()
        try:
            return _forward_secure_backend_iot_request(
                method=method,
                path=path,
                json_data=json_data,
                params=params,
            )
        except (httpx.HTTPError, CryptoError, ValueError):
            _discard_backend_iot_sessions()
            raise
    except (httpx.HTTPError, CryptoError, ValueError):
        _discard_backend_iot_sessions()
        raise


def _forward_secure_backend_iot_request(
    *,
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Encrypt, send, sequence-check, and decrypt one backend-IoT request/response."""

    session = get_or_create_backend_iot_session()
    with session.lock:
        # One lock protects both directions because the current protocol requires strict
        # in-order request/response handling per session.
        seq = session.replay.state_for(Direction.CLIENT_TO_SERVER).allocate_send_seq()
        request_envelope = encrypt_envelope(
            {
                "method": method,
                "path": path,
                "json": json_data,
                "params": params,
            },
            session.keys,
            session.transcript.protocol_version,
            session.transcript.session_id,
            Direction.CLIENT_TO_SERVER,
            seq=seq,
        )
        response = client.post(
            _iot_url("/secure/backend-iot/request"),
            json=request_envelope.to_dict(),
        )
        response.raise_for_status()
        response_envelope = SecureEnvelope.from_dict(response.json())
        session.replay.state_for(Direction.SERVER_TO_CLIENT).accept_recv_seq(
            response_envelope.seq
        )
        response_body = decrypt_envelope(
            response_envelope,
            session.keys,
            session.transcript.protocol_version,
            Direction.SERVER_TO_CLIENT,
            max_skew_ms=settings.max_skew_ms,
        )

    status_code = response_body.get("status_code")
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        raise ValueError("secure response missing status_code")
    return status_code, response_body.get("body")


def _iot_url(path: str) -> str:
    return f"{IOT_SERVER_URL.rstrip('/')}{path}"


def _discard_backend_iot_sessions() -> None:
    """Drop local session state after ambiguous secure transport failure."""

    with session_creation_lock:
        session_store.clear()


def _start_to_payload(start: HandshakeStart) -> dict[str, Any]:
    return {
        "role": start.role,
        "session_id": start.session_id,
        "client_identity": start.client_identity,
        "server_identity": start.server_identity,
        "client_key_id": start.client_key_id,
        "server_key_id": start.server_key_id,
        "client_ephemeral_pubkey": b64encode(start.client_ephemeral_pubkey),
        "timestamp_ms": start.timestamp_ms,
    }


def _validate_start_response(start: HandshakeStart, data: dict[str, Any]) -> None:
    """Ensure the IoT server echoed all client-controlled transcript fields exactly."""

    expected = {
        "role": start.role,
        "session_id": start.session_id,
        "client_identity": start.client_identity,
        "server_identity": start.server_identity,
        "client_key_id": start.client_key_id,
        "server_key_id": start.server_key_id,
        "client_ephemeral_pubkey": b64encode(start.client_ephemeral_pubkey),
        "timestamp_ms": start.timestamp_ms,
        "protocol_version": settings.protocol_version,
        "algorithm_suite": settings.algorithm_suite,
    }
    for field, value in expected.items():
        if data.get(field) != value:
            raise ValueError(f"handshake response field mismatch: {field}")
