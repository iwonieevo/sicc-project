from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .encoding import (
    b64decode,
    b64encode,
    concat,
    encode_u96,
    encode_uint64,
    encode_var,
)
from .errors import (
    DecodeError,
    DecryptionError,
    SignatureVerificationError,
    StaleMessageError,
)

DEFAULT_PROTOCOL_VERSION = "SICC-SECURE/1"
DEFAULT_ALGORITHM_SUITE = "X25519+Ed25519+HKDF-SHA256+AES-256-GCM"
AES_GCM_KEY_SIZE = 32
AES_GCM_NONCE_SIZE = 12
AES_GCM_TAG_SIZE = 16
SESSION_KEY_MATERIAL_SIZE = 88


class Direction(StrEnum):
    """Message direction within a secure session."""

    CLIENT_TO_SERVER = "client->server"
    SERVER_TO_CLIENT = "server->client"


AAD_DIRECTION_CLIENT_TO_SERVER = Direction.CLIENT_TO_SERVER
AAD_DIRECTION_SERVER_TO_CLIENT = Direction.SERVER_TO_CLIENT


@dataclass(frozen=True)
class AlgorithmSuite:
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    algorithm_suite: str = DEFAULT_ALGORITHM_SUITE


@dataclass(frozen=True)
class KeyPair:
    private_key: bytes
    public_key: bytes


@dataclass(frozen=True)
class HandshakeTranscript:
    protocol_version: str
    role: str
    algorithm_suite: str
    session_id: str
    client_identity: str
    server_identity: str
    client_key_id: str
    server_key_id: str
    server_ephemeral_pubkey: bytes
    client_ephemeral_pubkey: bytes
    timestamp_ms: int

    def encode(self) -> bytes:
        """Encode the transcript exactly as signed and fed into HKDF salt derivation."""

        _require_len("server_ephemeral_pubkey", self.server_ephemeral_pubkey, 32)
        _require_len("client_ephemeral_pubkey", self.client_ephemeral_pubkey, 32)

        return concat(
            [
                encode_var(self.protocol_version),
                encode_var(self.role),
                encode_var(self.algorithm_suite),
                encode_var(self.session_id),
                encode_var(self.client_identity),
                encode_var(self.server_identity),
                encode_var(self.client_key_id),
                encode_var(self.server_key_id),
                self.server_ephemeral_pubkey,
                self.client_ephemeral_pubkey,
                encode_uint64(self.timestamp_ms),
            ]
        )

    def digest(self) -> bytes:
        """Return SHA-256(transcript), used as the HKDF salt."""

        return hashlib.sha256(self.encode()).digest()


@dataclass(frozen=True)
class DerivedKeys:
    client_write_key: bytes
    server_write_key: bytes
    client_nonce_base: bytes
    server_nonce_base: bytes

    def write_key(self, direction: Direction) -> bytes:
        """Select the AES-GCM write key for one message direction."""

        return (
            self.client_write_key
            if direction == Direction.CLIENT_TO_SERVER
            else self.server_write_key
        )

    def nonce_base(self, direction: Direction) -> bytes:
        """Select the deterministic nonce base for one message direction."""

        return (
            self.client_nonce_base
            if direction == Direction.CLIENT_TO_SERVER
            else self.server_nonce_base
        )


@dataclass(frozen=True)
class SecureEnvelope:
    session_id: str
    seq: int
    ciphertext: str
    tag: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "ciphertext": self.ciphertext,
            "tag": self.tag,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecureEnvelope":
        try:
            session_id = data["session_id"]
            seq = data["seq"]
            ciphertext = data["ciphertext"]
            tag = data["tag"]
        except KeyError as exc:
            raise DecodeError(f"missing envelope field: {exc.args[0]}") from exc

        if not isinstance(session_id, str):
            raise DecodeError("session_id must be a string")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise DecodeError("seq must be an integer")
        if not isinstance(ciphertext, str) or not isinstance(tag, str):
            raise DecodeError("ciphertext and tag must be base64 strings")

        return cls(session_id=session_id, seq=seq, ciphertext=ciphertext, tag=tag)


def generate_ed25519_keypair() -> KeyPair:
    private = ed25519.Ed25519PrivateKey.generate()
    return KeyPair(
        private_key=private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        public_key=private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )


def ed25519_public_key_from_private_key(private_key: bytes) -> bytes:
    """Derive the raw Ed25519 public key bytes for a raw private key."""

    _require_len("private_key", private_key, 32)

    private = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def generate_x25519_keypair() -> KeyPair:
    private = x25519.X25519PrivateKey.generate()
    return KeyPair(
        private_key=private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        public_key=private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )


def public_key_id(public_key: bytes) -> str:
    """Return a compact stable identifier for looking up a registered Ed25519 public key."""

    _require_len("public_key", public_key, 32)

    return b64encode(hashlib.sha256(public_key).digest()[:16])


def sign_transcript(private_key: bytes, transcript: HandshakeTranscript) -> bytes:
    """Sign the full handshake transcript with a long-term Ed25519 private key."""

    _require_len("private_key", private_key, 32)

    key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
    return key.sign(transcript.encode())


def verify_transcript_signature(
    public_key: bytes, transcript: HandshakeTranscript, signature: bytes
) -> None:
    """Verify that the peer signed the exact transcript used for this session."""

    _require_len("public_key", public_key, 32)

    try:
        ed25519.Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, transcript.encode()
        )
    except InvalidSignature as exc:
        raise SignatureVerificationError("invalid transcript signature") from exc


def derive_session_keys(
    own_ephemeral_private_key: bytes,
    peer_ephemeral_public_key: bytes,
    transcript: HandshakeTranscript,
    info: bytes = b"sicc secure transport v1",
) -> DerivedKeys:
    """Derive directional AES-GCM keys and nonce bases from an X25519 shared secret."""

    _require_len("own_ephemeral_private_key", own_ephemeral_private_key, 32)
    _require_len("peer_ephemeral_public_key", peer_ephemeral_public_key, 32)

    shared_secret = x25519.X25519PrivateKey.from_private_bytes(
        own_ephemeral_private_key
    ).exchange(x25519.X25519PublicKey.from_public_bytes(peer_ephemeral_public_key))
    material = HKDF(
        algorithm=hashes.SHA256(),
        length=SESSION_KEY_MATERIAL_SIZE,
        salt=transcript.digest(),
        info=info,
    ).derive(shared_secret)

    return DerivedKeys(
        client_write_key=material[0:32],
        server_write_key=material[32:64],
        client_nonce_base=material[64:76],
        server_nonce_base=material[76:88],
    )


def encode_aad(
    protocol_version: str,
    session_id: str,
    direction: Direction,
    seq: int,
) -> bytes:
    """Encode the Additional Authenticated Data bound to every AES-GCM message."""

    return concat(
        [
            encode_var(protocol_version),
            encode_var(session_id),
            encode_var(direction),
            encode_u96(seq),
        ]
    )


def nonce_for(nonce_base: bytes, seq: int) -> bytes:
    """Construct the AES-GCM nonce as nonce_base XOR seq_as_96bit_big_endian."""

    _require_len("nonce_base", nonce_base, AES_GCM_NONCE_SIZE)
    seq_bytes = encode_u96(seq)
    return bytes(left ^ right for left, right in zip(nonce_base, seq_bytes))


def encrypt_envelope(
    plaintext_body: dict[str, Any],
    keys: DerivedKeys,
    protocol_version: str,
    session_id: str,
    direction: Direction,
    seq: int,
    now_ms: int | None = None,
) -> SecureEnvelope:
    """Encrypt a JSON-compatible body into the transport envelope."""

    body = dict(plaintext_body)
    body.setdefault(
        "timestamp_ms", int(time.time() * 1000) if now_ms is None else now_ms
    )
    plaintext = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    aad = encode_aad(protocol_version, session_id, direction, seq)
    nonce = nonce_for(keys.nonce_base(direction), seq)
    encrypted = AESGCM(keys.write_key(direction)).encrypt(nonce, plaintext, aad)
    return SecureEnvelope(
        session_id=session_id,
        seq=seq,
        ciphertext=b64encode(encrypted[:-AES_GCM_TAG_SIZE]),
        tag=b64encode(encrypted[-AES_GCM_TAG_SIZE:]),
    )


def decrypt_envelope(
    envelope: SecureEnvelope,
    keys: DerivedKeys,
    protocol_version: str,
    direction: Direction,
    max_skew_ms: int = 30_000,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Decrypt and authenticate an envelope, then enforce timestamp freshness."""

    try:
        encrypted = b64decode(envelope.ciphertext) + b64decode(envelope.tag)
    except Exception as exc:
        raise DecodeError("invalid envelope base64") from exc

    aad = encode_aad(protocol_version, envelope.session_id, direction, envelope.seq)
    nonce = nonce_for(keys.nonce_base(direction), envelope.seq)
    try:
        plaintext = AESGCM(keys.write_key(direction)).decrypt(nonce, encrypted, aad)
    except Exception as exc:
        raise DecryptionError("authenticated decryption failed") from exc

    try:
        body = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise DecodeError("decrypted body is not valid JSON") from exc

    timestamp_ms = body.get("timestamp_ms")
    if not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool):
        raise DecodeError("decrypted body is missing integer timestamp_ms")

    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if current_ms - timestamp_ms > max_skew_ms:
        raise StaleMessageError("message timestamp is too old")

    return body


def _require_len(name: str, value: bytes, expected: int) -> None:
    assert len(value) == expected, f"{name} must be {expected} bytes"
