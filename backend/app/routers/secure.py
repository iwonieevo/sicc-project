import logging
from typing import Any

import httpx
from app.auth import get_current_user
from app.plaintext_security import (
    INTERNAL_FRONTEND_TOKEN,
    INTERNAL_FRONTEND_TOKEN_HEADER,
)
from app.secure_transport import initiate_backend_iot_handshake, settings
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from security import (
    ROLE_FRONTEND_BACKEND,
    CryptoError,
    Direction,
    HandshakeStart,
    SecureEnvelope,
    SecureSession,
    SecureSessionStore,
    create_server_authenticated_handshake,
    decode_handshake_field,
    decrypt_envelope,
    ed25519_public_key_from_private_key,
    encrypt_envelope,
)
from security.encoding import b64encode

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/secure", tags=["secure-transport"])
frontend_session_store = SecureSessionStore()
local_client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0)


class BackendIotHandshakeResponse(BaseModel):
    session_id: str
    status: str


class FrontendBackendConfigResponse(BaseModel):
    secure_mode: bool
    protocol_version: str
    algorithm_suite: str
    server_identity: str
    server_key_id: str | None
    server_public_key: str | None
    max_skew_ms: int
    tofu_allowed: bool


class FrontendBackendHandshakeStartRequest(BaseModel):
    role: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    client_ephemeral_pubkey: str
    timestamp_ms: int


class FrontendBackendHandshakeStartResponse(BaseModel):
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


class FrontendBackendEncryptedRequest(BaseModel):
    session_id: str
    seq: int
    ciphertext: str
    tag: str


@router.post("/backend-iot/handshake", response_model=BackendIotHandshakeResponse)
def create_backend_iot_handshake(_current_user: dict = Depends(get_current_user)):
    """Diagnostic endpoint that manually triggers the backend-IoT handshake."""

    try:
        session = initiate_backend_iot_handshake()
    except httpx.HTTPStatusError as exc:
        LOGGER.warning(
            "IoT server rejected backend-IoT secure handshake: %s",
            exc.response.status_code,
        )
        raise HTTPException(status_code=502, detail="secure handshake failed") from exc
    except httpx.HTTPError as exc:
        LOGGER.warning("IoT server unavailable during secure handshake: %s", exc)
        raise HTTPException(status_code=503, detail="IoT server unavailable") from exc
    except (CryptoError, ValueError, AssertionError) as exc:
        LOGGER.warning("Backend-IoT secure handshake failed: %s", exc)
        raise HTTPException(status_code=400, detail="secure handshake failed") from exc

    return BackendIotHandshakeResponse(
        session_id=session.transcript.session_id,
        status="established",
    )


@router.get("/frontend-backend/config", response_model=FrontendBackendConfigResponse)
def get_frontend_backend_config():
    """Expose backend identity metadata needed by the browser secure client."""

    public_key = None
    if settings.private_key is not None:
        public_key = b64encode(
            ed25519_public_key_from_private_key(settings.private_key)
        )

    return FrontendBackendConfigResponse(
        secure_mode=settings.enabled,
        protocol_version=settings.protocol_version,
        algorithm_suite=settings.algorithm_suite,
        server_identity=settings.identity,
        server_key_id=settings.key_id,
        server_public_key=public_key,
        max_skew_ms=settings.max_skew_ms,
        tofu_allowed=True,
    )


@router.post(
    "/frontend-backend/handshake/start",
    response_model=FrontendBackendHandshakeStartResponse,
)
def start_frontend_backend_handshake(request: FrontendBackendHandshakeStartRequest):
    """Start a server-authenticated encrypted session for a browser client."""

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
            expected_role=ROLE_FRONTEND_BACKEND,
            expected_server_identity=settings.identity,
        )
    except Exception as exc:
        _raise_secure_transport_error(exc)

    frontend_session_store.put(
        SecureSession(transcript=handshake.transcript, keys=handshake.keys)
    )
    LOGGER.info(
        "Started frontend-backend secure session %s",
        handshake.transcript.session_id,
    )
    return FrontendBackendHandshakeStartResponse(
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


@router.post("/frontend-backend/request")
def handle_encrypted_frontend_backend_request(request: FrontendBackendEncryptedRequest):
    """Decrypt one browser API request, dispatch it locally, and encrypt the response."""

    envelope = SecureEnvelope(
        session_id=request.session_id,
        seq=request.seq,
        ciphertext=request.ciphertext,
        tag=request.tag,
    )
    session = frontend_session_store.get(envelope.session_id)
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
            response_body = _dispatch_frontend_plaintext_request(request_body)
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
            _raise_secure_transport_error(exc)


def _dispatch_frontend_plaintext_request(body: dict[str, Any]) -> dict[str, Any]:
    method = body.get("method")
    path = body.get("path")
    json_data = body.get("json")
    params = body.get("params")
    headers = body.get("headers") or {}

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("unsupported frontend method")
    if (
        not isinstance(path, str)
        or not path.startswith("/api/")
        or path.startswith("/api/secure/")
        or "?" in path
        or "#" in path
        or "\\" in path
    ):
        raise ValueError("unsupported frontend path")
    if json_data is not None and not isinstance(json_data, dict):
        raise ValueError("frontend json must be an object")
    if params is not None and not isinstance(params, dict):
        raise ValueError("frontend params must be an object")
    if not isinstance(headers, dict):
        raise ValueError("frontend headers must be an object")

    forwarded_headers = {
        key: value
        for key, value in headers.items()
        if isinstance(key, str)
        and isinstance(value, str)
        and key.lower() in {"authorization", "content-type"}
    }
    forwarded_headers[INTERNAL_FRONTEND_TOKEN_HEADER] = INTERNAL_FRONTEND_TOKEN
    response = local_client.request(
        method=method,
        url=path,
        json=json_data,
        params=params,
        headers=forwarded_headers,
    )
    try:
        response_body = response.json()
    except ValueError:
        response_body = {"message": response.text}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }


def _raise_secure_transport_error(exc: Exception) -> None:
    if isinstance(exc, (CryptoError, ValueError, AssertionError)):
        LOGGER.warning("Frontend-backend secure transport failed: %s", exc)
        raise HTTPException(status_code=400, detail="secure transport failed") from exc
    raise exc
