import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import unquote

import httpx
from app.agent_security import (
    AGENT_IDENTITY_HEADER,
    INTERNAL_BACKEND_TOKEN,
    INTERNAL_BACKEND_TOKEN_HEADER,
    INTERNAL_AGENT_TOKEN,
    INTERNAL_AGENT_TOKEN_HEADER,
)
from app.database import get_db
from app.models import Device
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from security import (
    ROLE_AGENT_ENROLLMENT,
    ROLE_AGENT_IOT,
    ROLE_BACKEND_IOT,
    CryptoError,
    Direction,
    HandshakeStart,
    SecureEnvelope,
    SecureSession,
    SecureSessionStore,
    SecureTransportSettings,
    ServerHandshake,
    create_server_handshake,
    create_server_authenticated_handshake,
    decode_handshake_field,
    decrypt_envelope,
    encrypt_envelope,
    load_secure_transport_settings,
    public_key_id,
    verify_client_handshake_signature,
)
from security.encoding import b64decode, b64encode

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/secure/backend-iot", tags=["secure-transport"])
agent_iot_router = APIRouter(prefix="/secure/agent-iot", tags=["secure-transport"])
agent_enrollment_router = APIRouter(
    prefix="/secure/agent-enrollment", tags=["secure-transport"]
)

settings = load_secure_transport_settings(default_identity="iot-server")

session_store = SecureSessionStore()
agent_session_store = SecureSessionStore()
agent_enrollment_session_store = SecureSessionStore()

local_client = httpx.Client(base_url="http://127.0.0.1:7000", timeout=10.0)


PENDING_HANDSHAKE_TTL_SECONDS = int(os.getenv("SICC_PENDING_HANDSHAKE_TTL_SECONDS", "60"))


@dataclass(frozen=True)
class PendingAgentHandshake:
    handshake: ServerHandshake
    verifier_settings: SecureTransportSettings


class PendingHandshakeStore:
    """Tiny in-memory pending handshake store with lazy TTL cleanup."""

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[float, Any]] = {}

    def put(self, session_id: str, value: Any) -> None:
        self.prune()
        self._values[session_id] = (time.monotonic(), value)

    def pop(self, session_id: str) -> Any | None:
        self.prune()
        item = self._values.pop(session_id, None)
        if item is None:
            return None
        return item[1]

    def prune(self) -> None:
        if self.ttl_seconds < 1:
            self._values.clear()
            return
        cutoff = time.monotonic() - self.ttl_seconds
        stale = [
            session_id
            for session_id, (created_at, _) in self._values.items()
            if created_at < cutoff
        ]
        for session_id in stale:
            self._values.pop(session_id, None)


pending_handshakes = PendingHandshakeStore(PENDING_HANDSHAKE_TTL_SECONDS)
pending_agent_handshakes = PendingHandshakeStore(PENDING_HANDSHAKE_TTL_SECONDS)


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


class AgentIotHandshakeStartRequest(BaseModel):
    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    client_ephemeral_pubkey: str
    timestamp_ms: int


class AgentIotHandshakeStartResponse(BaseModel):
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


class AgentIotHandshakeFinishRequest(BaseModel):
    session_id: str
    client_signature: str


class AgentIotHandshakeFinishResponse(BaseModel):
    session_id: str
    status: str


class AgentIotEncryptedRequest(BaseModel):
    session_id: str
    seq: int
    ciphertext: str
    tag: str


class AgentEnrollmentHandshakeStartRequest(BaseModel):
    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    client_ephemeral_pubkey: str
    timestamp_ms: int


class AgentEnrollmentHandshakeStartResponse(BaseModel):
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


class AgentEnrollmentEncryptedRequest(BaseModel):
    session_id: str
    seq: int
    ciphertext: str
    tag: str


@router.post("/handshake/start", response_model=BackendIotHandshakeStartResponse)
def start_backend_iot_handshake(request: BackendIotHandshakeStartRequest):
    """Accept the backend's start message and return the signed server transcript."""

    try:
        client_ephemeral_pubkey = decode_handshake_field(
            request.client_ephemeral_pubkey
        )
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

    pending_handshakes.put(handshake.transcript.session_id, handshake)
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

    handshake = pending_handshakes.pop(request.session_id)
    if handshake is None:
        raise HTTPException(status_code=404, detail="handshake not found")

    try:
        client_signature = decode_handshake_field(request.client_signature)
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
            recv_state = session.replay.state_for(Direction.CLIENT_TO_SERVER)
            recv_state.check_recv_seq(envelope.seq)
            request_body = decrypt_envelope(
                envelope,
                session.keys,
                session.transcript.protocol_version,
                Direction.CLIENT_TO_SERVER,
                max_skew_ms=settings.max_skew_ms,
            )
            recv_state.accept_recv_seq(envelope.seq)
            response_body = _dispatch_plaintext_request(request_body)
            seq = session.replay.state_for(
                Direction.SERVER_TO_CLIENT
            ).allocate_send_seq()
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


@agent_iot_router.post(
    "/handshake/start", response_model=AgentIotHandshakeStartResponse
)
def start_agent_iot_handshake(
    request: AgentIotHandshakeStartRequest, db: Session = Depends(get_db)
):
    """Accept an agent start message and verify its registered device key."""

    try:
        client_ephemeral_pubkey = decode_handshake_field(
            request.client_ephemeral_pubkey
        )
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
        verifier_settings = _settings_trusting_registered_device(db, start)
        handshake = create_server_handshake(
            verifier_settings,
            start,
            expected_role=ROLE_AGENT_IOT,
            expected_client_identity=start.client_identity,
            expected_server_identity=settings.identity,
        )
    except Exception as exc:
        _raise_handshake_error(exc)

    pending_agent_handshakes.put(
        handshake.transcript.session_id,
        PendingAgentHandshake(
            handshake=handshake,
            verifier_settings=verifier_settings,
        ),
    )
    LOGGER.info(
        "Started agent-IoT secure handshake session %s for %s",
        handshake.transcript.session_id,
        handshake.transcript.client_identity,
    )
    return AgentIotHandshakeStartResponse(
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


@agent_iot_router.post(
    "/handshake/finish", response_model=AgentIotHandshakeFinishResponse
)
def finish_agent_iot_handshake(request: AgentIotHandshakeFinishRequest):
    """Verify the agent transcript signature and promote the pending session."""

    pending = pending_agent_handshakes.pop(request.session_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="handshake not found")

    try:
        client_signature = decode_handshake_field(request.client_signature)
        verify_client_handshake_signature(
            pending.verifier_settings,
            pending.handshake.transcript,
            client_signature,
        )
    except Exception as exc:
        _raise_handshake_error(exc)

    agent_session_store.put(
        SecureSession(
            transcript=pending.handshake.transcript, keys=pending.handshake.keys
        )
    )
    LOGGER.info(
        "Finished agent-IoT secure handshake session %s for %s",
        pending.handshake.transcript.session_id,
        pending.handshake.transcript.client_identity,
    )
    return AgentIotHandshakeFinishResponse(
        session_id=pending.handshake.transcript.session_id,
        status="established",
    )


@agent_iot_router.post("/request")
def handle_encrypted_agent_iot_request(request: AgentIotEncryptedRequest):
    """Decrypt an agent request, dispatch it locally, and encrypt the response."""

    envelope = SecureEnvelope(
        session_id=request.session_id,
        seq=request.seq,
        ciphertext=request.ciphertext,
        tag=request.tag,
    )
    session = agent_session_store.get(envelope.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="secure session not found")

    with session.lock:
        try:
            recv_state = session.replay.state_for(Direction.CLIENT_TO_SERVER)
            recv_state.check_recv_seq(envelope.seq)
            request_body = decrypt_envelope(
                envelope,
                session.keys,
                session.transcript.protocol_version,
                Direction.CLIENT_TO_SERVER,
                max_skew_ms=settings.max_skew_ms,
            )
            recv_state.accept_recv_seq(envelope.seq)
            response_body = _dispatch_agent_plaintext_request(
                request_body, session.transcript.client_identity
            )
            seq = session.replay.state_for(
                Direction.SERVER_TO_CLIENT
            ).allocate_send_seq()
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


@agent_enrollment_router.post(
    "/handshake/start", response_model=AgentEnrollmentHandshakeStartResponse
)
def start_agent_enrollment_handshake(request: AgentEnrollmentHandshakeStartRequest):
    """Start a server-authenticated encrypted session for first agent enrollment."""

    try:
        client_ephemeral_pubkey = decode_handshake_field(
            request.client_ephemeral_pubkey
        )
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
        handshake = create_server_authenticated_handshake(
            settings,
            start,
            expected_role=ROLE_AGENT_ENROLLMENT,
            expected_server_identity=settings.identity,
        )
    except Exception as exc:
        _raise_handshake_error(exc)

    agent_enrollment_session_store.put(
        SecureSession(transcript=handshake.transcript, keys=handshake.keys)
    )
    LOGGER.info(
        "Started agent enrollment secure session %s for %s",
        handshake.transcript.session_id,
        handshake.transcript.client_identity,
    )
    return AgentEnrollmentHandshakeStartResponse(
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


@agent_enrollment_router.post("/request")
def handle_encrypted_agent_enrollment_request(request: AgentEnrollmentEncryptedRequest):
    """Decrypt a first-enrollment request and dispatch only agent registration."""

    agent_enrollment_session_store.prune_older_than(PENDING_HANDSHAKE_TTL_SECONDS)
    envelope = SecureEnvelope(
        session_id=request.session_id,
        seq=request.seq,
        ciphertext=request.ciphertext,
        tag=request.tag,
    )
    session = agent_enrollment_session_store.get(envelope.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="secure session not found")

    with session.lock:
        try:
            recv_state = session.replay.state_for(Direction.CLIENT_TO_SERVER)
            recv_state.check_recv_seq(envelope.seq)
            request_body = decrypt_envelope(
                envelope,
                session.keys,
                session.transcript.protocol_version,
                Direction.CLIENT_TO_SERVER,
                max_skew_ms=settings.max_skew_ms,
            )
            recv_state.accept_recv_seq(envelope.seq)
            response_body = _dispatch_agent_enrollment_plaintext_request(
                request_body,
                session.transcript.client_identity,
            )
            seq = session.replay.state_for(
                Direction.SERVER_TO_CLIENT
            ).allocate_send_seq()
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
        LOGGER.warning("Secure transport failed: %s", exc)
        raise HTTPException(status_code=400, detail="secure transport failed") from exc
    raise exc


def _settings_trusting_registered_device(
    db: Session, start: HandshakeStart
) -> SecureTransportSettings:
    if start.role != ROLE_AGENT_IOT:
        raise ValueError("unexpected handshake role")

    device = (
        db.query(Device)
        .filter(Device.name == start.client_identity, Device.is_deleted == False)
        .first()
    )
    if device is None:
        raise ValueError("unknown device identity")
    if device.public_key_id is None or device.public_key is None:
        raise ValueError("device public key is not provisioned")
    if device.public_key_id != start.client_key_id:
        raise ValueError("device public key id mismatch")

    try:
        public_key = b64decode(device.public_key)
    except Exception as exc:
        raise ValueError("registered device public key is invalid") from exc
    if len(public_key) != 32:
        raise ValueError("registered device public key has invalid length")
    if public_key_id(public_key) != start.client_key_id:
        raise ValueError("registered device public key id is invalid")

    trusted_public_keys = dict(settings.trusted_public_keys)
    trusted_public_keys[start.client_key_id] = public_key
    return replace(settings, trusted_public_keys=trusted_public_keys)


def _dispatch_plaintext_request(body: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a decrypted request to the existing IoT HTTP routes in-process."""

    method = body.get("method")
    path = body.get("path")
    json_data = body.get("json")
    params = body.get("params")

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("unsupported forwarded method")
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("/secure/")
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
        headers={INTERNAL_BACKEND_TOKEN_HEADER: INTERNAL_BACKEND_TOKEN},
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": response.text}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }


def _dispatch_agent_plaintext_request(
    body: dict[str, Any], agent_identity: str
) -> dict[str, Any]:
    """Dispatch a decrypted agent request to the existing agent routes."""

    method = body.get("method")
    path = body.get("path")
    json_data = body.get("json")
    params = body.get("params")

    if method not in {"GET", "POST"}:
        raise ValueError("unsupported forwarded agent method")
    if not _is_allowed_agent_forward(method, path):
        raise ValueError("unsupported forwarded agent path")
    if json_data is not None and not isinstance(json_data, dict):
        raise ValueError("forwarded agent json must be an object")
    if params is not None and not isinstance(params, dict):
        raise ValueError("forwarded agent params must be an object")

    response = local_client.request(
        method=method,
        url=path,
        json=json_data,
        params=params,
        headers={
            INTERNAL_AGENT_TOKEN_HEADER: INTERNAL_AGENT_TOKEN,
            AGENT_IDENTITY_HEADER: agent_identity,
        },
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": response.text}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }


def _dispatch_agent_enrollment_plaintext_request(
    body: dict[str, Any], agent_identity: str
) -> dict[str, Any]:
    method = body.get("method")
    path = body.get("path")
    json_data = body.get("json")

    if method != "POST" or path != "/agent/register":
        raise ValueError("unsupported forwarded enrollment path")
    if json_data is not None and not isinstance(json_data, dict):
        raise ValueError("forwarded enrollment json must be an object")
    if not isinstance(json_data, dict):
        raise ValueError("forwarded enrollment json is required")

    response = local_client.request(
        method=method,
        url=path,
        json=json_data,
        headers={
            INTERNAL_AGENT_TOKEN_HEADER: INTERNAL_AGENT_TOKEN,
            AGENT_IDENTITY_HEADER: agent_identity,
        },
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": response.text}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }


def _is_allowed_agent_forward(method: str, path: Any) -> bool:
    if not isinstance(path, str):
        return False
    if "?" in path or "#" in path or "\\" in path:
        return False
    if unquote(path) != path:
        return False

    segments = path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        return False

    if method == "POST" and path == "/agent/callback":
        return True

    if method != "GET":
        return False
    if len(segments) != 4:
        return False
    _, prefix, device_id, action = segments
    return (
        prefix == "agent"
        and device_id.isdecimal()
        and int(device_id) > 0
        and action == "commands"
    )
