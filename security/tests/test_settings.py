import json

import pytest

from security import (
    SecureTransportSettings,
    generate_ed25519_keypair,
    load_secure_transport_settings,
    public_key_id,
)
from security.encoding import b64encode


def test_disabled_settings_use_safe_defaults():
    settings = load_secure_transport_settings(default_identity="backend", env={})

    assert isinstance(settings, SecureTransportSettings)
    assert settings.enabled is False
    assert settings.identity == "backend"
    assert settings.private_key is None
    assert settings.trusted_public_keys == {}
    assert settings.max_skew_ms == 30_000


def test_enabled_settings_load_private_key_and_trusted_keys():
    own = generate_ed25519_keypair()
    peer = generate_ed25519_keypair()
    peer_id = public_key_id(peer.public_key)
    env = {
        "SECURE_MODE": "true",
        "SICC_SERVICE_IDENTITY": "backend",
        "SICC_SERVICE_KEY_ID": public_key_id(own.public_key),
        "SICC_SERVICE_PRIVATE_KEY_B64": b64encode(own.private_key),
        "SICC_TRUSTED_PUBLIC_KEYS_JSON": json.dumps({peer_id: b64encode(peer.public_key)}),
    }

    settings = load_secure_transport_settings(default_identity="unused", env=env)

    assert settings.enabled is True
    assert settings.identity == "backend"
    assert settings.private_key == own.private_key
    assert settings.trusted_public_key(peer_id) == peer.public_key


def test_enabled_settings_require_private_key():
    with pytest.raises(ValueError, match="SICC_SERVICE_PRIVATE_KEY_B64"):
        load_secure_transport_settings(
            default_identity="backend",
            env={"SECURE_MODE": "true", "SICC_SERVICE_KEY_ID": "key-id"},
        )


def test_trusted_public_key_id_must_match_public_key_bytes():
    peer = generate_ed25519_keypair()
    env = {
        "SICC_TRUSTED_PUBLIC_KEYS_JSON": json.dumps({"wrong": b64encode(peer.public_key)}),
    }

    with pytest.raises(ValueError, match="does not match"):
        load_secure_transport_settings(default_identity="backend", env=env)


def test_trusted_public_key_lookup_fails_closed():
    settings = load_secure_transport_settings(default_identity="backend", env={})

    with pytest.raises(ValueError, match="unknown trusted public key id"):
        settings.trusted_public_key("missing")
