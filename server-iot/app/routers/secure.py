import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from security import (
    ROLE_BACKEND_IOT,
    CryptoError,
    Direction,
    HandshakeStart,
    SecureEnvelope,
    SecureSession,
    SecureSessionStore,
    ServerHandshake,
    create_server_handshake,
    decrypt_envelope,
    encrypt_envelope,
    load_secure_transport_settings,
    verify_client_handshake_signature,
)
from security.encoding import b64decode, b64encode

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/secure/backend-iot", tags=["secure-transport"])
settings = load_secure_transport_settings(default_identity="iot-server")
session_store = SecureSessionStore()
local_client = httpx.Client(base_url="http://127.0.0.1:7000", timeout=10.0)


pending_handshakes: dict[str, ServerHandshake] = {}


class BackendIotHandshakeStartRequest(BaseModel):
    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    client_ephemeral_pubkey: str
    timestamp_ms: int


class BackendIotHandshakeStartResponse(BaseModel):
    protocol_version: str
    algorithm_suite: str
    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    server_ephemeral_pubkey: str
    client_ephemeral_pubkey: str
    timestamp_ms: int
    server_signature: str


class BackendIotHandshakeFinishRequest(BaseModel):
    session_id: str
    client_signature: str


class BackendIotHandshakeFinishResponse(BaseModel):
    session_id: str
    status: str


class BackendIotEncryptedRequest(BaseModel):
    session_id: str
    seq: int
    ciphertext: str
    tag: str


@router.post("/handshake/start", response_model=BackendIotHandshakeStartResponse)
def start_backend_iot_handshake(request: BackendIotHandshakeStartRequest):
    """Accept the backend's start message and return the signed server transcript."""

    try:
        client_ephemeral_pubkey = _decode_b64_field(request.client_ephemeral_pubkey)
        start = HandshakeStart(
            role=request.role,
            session_id=request.session_id,
            client_identity=request.client_identity,
            server_identity=request.server_identity,
            client_key_id=request.client_key_id,
            server_key_id=request.server_key_id,
            client_ephemeral_pubkey=client_ephemeral_pubkey,
            timestamp_ms=request.timestamp_ms,
        )
        handshake = create_server_handshake(
            settings,
            start,
            expected_role=ROLE_BACKEND_IOT,
            expected_client_identity="backend",
            expected_server_identity=settings.identity,
        )
    except Exception as exc:
        _raise_handshake_error(exc)

    pending_handshakes[handshake.transcript.session_id] = handshake
    LOGGER.info(
        "Started backend-IoT secure handshake session %s",
        handshake.transcript.session_id,
    )
    return BackendIotHandshakeStartResponse(
        protocol_version=handshake.transcript.protocol_version,
        algorithm_suite=handshake.transcript.algorithm_suite,
        role=handshake.transcript.role,
        session_id=handshake.transcript.session_id,
        client_identity=handshake.transcript.client_identity,
        server_identity=handshake.transcript.server_identity,
        client_key_id=handshake.transcript.client_key_id,
        server_key_id=handshake.transcript.server_key_id,
        server_ephemeral_pubkey=b64encode(handshake.transcript.server_ephemeral_pubkey),
        client_ephemeral_pubkey=b64encode(handshake.transcript.client_ephemeral_pubkey),
        timestamp_ms=handshake.transcript.timestamp_ms,
        server_signature=b64encode(handshake.server_signature),
    )


@router.post("/handshake/finish", response_model=BackendIotHandshakeFinishResponse)
def finish_backend_iot_handshake(request: BackendIotHandshakeFinishRequest):
    """Verify the backend's transcript signature and promote the pending session."""

    handshake = pending_handshakes.pop(request.session_id, None)
    if handshake is None:
        raise HTTPException(status_code=404, detail="handshake not found")

    try:
        client_signature = _decode_b64_field(request.client_signature)
        verify_client_handshake_signature(
            settings,
            handshake.transcript,
            client_signature,
        )
    except Exception as exc:
        _raise_handshake_error(exc)

    session_store.put(
        SecureSession(transcript=handshake.transcript, keys=handshake.keys)
    )
    LOGGER.info(
        "Finished backend-IoT secure handshake session %s",
        handshake.transcript.session_id,
    )
    return BackendIotHandshakeFinishResponse(
        session_id=handshake.transcript.session_id,
        status="established",
    )


@router.post("/request")
def handle_encrypted_backend_iot_request(request: BackendIotEncryptedRequest):
    """Decrypt a backend request, dispatch it locally, and encrypt the response."""

    envelope = SecureEnvelope(
        session_id=request.session_id,
        seq=request.seq,
        ciphertext=request.ciphertext,
        tag=request.tag,
    )
    session = session_store.get(envelope.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="secure session not found")

    with session.lock:
        try:
            # Sequence validation happens before decryption so replayed envelopes fail
            # even if their ciphertext would otherwise authenticate.
            session.replay.state_for(Direction.CLIENT_TO_SERVER).accept_recv_seq(
                envelope.seq
            )
            request_body = decrypt_envelope(
                envelope,
                session.keys,
                session.transcript.protocol_version,
                Direction.CLIENT_TO_SERVER,
                max_skew_ms=settings.max_skew_ms,
            )
            response_body = _dispatch_plaintext_request(request_body)
            seq = session.replay.state_for(Direction.SERVER_TO_CLIENT).allocate_send_seq()
            response_envelope = encrypt_envelope(
                response_body,
                session.keys,
                session.transcript.protocol_version,
                session.transcript.session_id,
                Direction.SERVER_TO_CLIENT,
                seq=seq,
            )
            return response_envelope.to_dict()
        except HTTPException:
            raise
        except Exception as exc:
            _raise_handshake_error(exc)


def _raise_handshake_error(exc: Exception) -> None:
    if isinstance(exc, (CryptoError, ValueError, AssertionError)):
        LOGGER.warning("Backend-IoT secure handshake failed: %s", exc)
        raise HTTPException(status_code=400, detail="secure handshake failed") from exc
    raise exc


def _decode_b64_field(value: str) -> bytes:
    try:
        return b64decode(value)
    except Exception as exc:
        raise ValueError("invalid handshake base64 field") from exc


def _dispatch_plaintext_request(body: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a decrypted request to the existing IoT HTTP routes in-process."""

    method = body.get("method")
    path = body.get("path")
    json_data = body.get("json")
    params = body.get("params")

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("unsupported forwarded method")
    if not isinstance(path, str) or not path.startswith("/") or path.startswith(
        "/secure/"
    ):
        raise ValueError("unsupported forwarded path")
    if json_data is not None and not isinstance(json_data, dict):
        raise ValueError("forwarded json must be an object")
    if params is not None and not isinstance(params, dict):
        raise ValueError("forwarded params must be an object")

    response = local_client.request(
        method=method,
        url=path,
        json=json_data,
        params=params,
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": response.text}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }
