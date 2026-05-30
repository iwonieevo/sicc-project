import json

import pytest

from security import (
    ROLE_BACKEND_IOT,
    SignatureVerificationError,
    StaleMessageError,
    complete_client_handshake,
    create_handshake_start,
    create_server_handshake,
    generate_ed25519_keypair,
    load_secure_transport_settings,
    public_key_id,
    verify_client_handshake_signature,
)
from security.encoding import b64encode


def _settings_pair():
    backend_key = generate_ed25519_keypair()
    iot_key = generate_ed25519_keypair()
    backend_key_id = public_key_id(backend_key.public_key)
    iot_key_id = public_key_id(iot_key.public_key)

    backend = load_secure_transport_settings(
        default_identity="backend",
        env={
            "SECURE_MODE": "true",
            "SICC_SERVICE_IDENTITY": "backend",
            "SICC_SERVICE_KEY_ID": backend_key_id,
            "SICC_SERVICE_PRIVATE_KEY_B64": b64encode(backend_key.private_key),
            "SICC_TRUSTED_PUBLIC_KEYS_JSON": json.dumps(
                {iot_key_id: b64encode(iot_key.public_key)}
            ),
        },
    )
    iot = load_secure_transport_settings(
        default_identity="iot-server",
        env={
            "SECURE_MODE": "true",
            "SICC_SERVICE_IDENTITY": "iot-server",
            "SICC_SERVICE_KEY_ID": iot_key_id,
            "SICC_SERVICE_PRIVATE_KEY_B64": b64encode(iot_key.private_key),
            "SICC_TRUSTED_PUBLIC_KEYS_JSON": json.dumps(
                {backend_key_id: b64encode(backend_key.public_key)}
            ),
        },
    )
    return backend, iot


def test_backend_iot_mutual_handshake_derives_matching_keys():
    backend, iot = _settings_pair()
    start, client_ephemeral = create_handshake_start(
        backend,
        role=ROLE_BACKEND_IOT,
        server_identity="iot-server",
        server_key_id=iot.key_id,
        timestamp_ms=1_800_000_000_000,
    )
    server = create_server_handshake(
        iot,
        start,
        expected_role=ROLE_BACKEND_IOT,
        expected_client_identity="backend",
        expected_server_identity="iot-server",
        timestamp_ms=1_800_000_000_001,
    )
    client = complete_client_handshake(
        backend,
        start,
        client_ephemeral,
        server_ephemeral_pubkey=server.transcript.server_ephemeral_pubkey,
        server_signature=server.server_signature,
        timestamp_ms=1_800_000_000_002,
    )

    verify_client_handshake_signature(
        iot,
        server.transcript,
        client.client_signature,
    )
    assert client.transcript == server.transcript
    assert client.keys == server.keys


def test_client_rejects_tampered_server_signature():
    backend, iot = _settings_pair()
    start, client_ephemeral = create_handshake_start(
        backend,
        role=ROLE_BACKEND_IOT,
        server_identity="iot-server",
        server_key_id=iot.key_id,
        timestamp_ms=1_800_000_000_000,
    )
    server = create_server_handshake(
        iot,
        start,
        expected_role=ROLE_BACKEND_IOT,
        expected_client_identity="backend",
        expected_server_identity="iot-server",
        timestamp_ms=1_800_000_000_001,
    )

    with pytest.raises(SignatureVerificationError):
        complete_client_handshake(
            backend,
            start,
            client_ephemeral,
            server_ephemeral_pubkey=server.transcript.server_ephemeral_pubkey,
            server_signature=server.server_signature + b"\x00",
            timestamp_ms=1_800_000_000_002,
        )


def test_server_rejects_stale_handshake_start():
    backend, iot = _settings_pair()
    start, _ = create_handshake_start(
        backend,
        role=ROLE_BACKEND_IOT,
        server_identity="iot-server",
        server_key_id=iot.key_id,
        timestamp_ms=1_800_000_000_000,
    )

    with pytest.raises(StaleMessageError):
        create_server_handshake(
            iot,
            start,
            expected_role=ROLE_BACKEND_IOT,
            expected_client_identity="backend",
            expected_server_identity="iot-server",
            timestamp_ms=1_800_000_030_001,
        )


def test_create_handshake_start_requires_secure_mode():
    settings = load_secure_transport_settings(default_identity="backend", env={})

    with pytest.raises(ValueError, match="secure transport is disabled"):
        create_handshake_start(
            settings,
            role=ROLE_BACKEND_IOT,
            server_identity="iot-server",
            server_key_id="missing",
        )
