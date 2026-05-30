from dataclasses import replace

import pytest

from security import (
    DecodeError,
    DecryptionError,
    Direction,
    HandshakeTranscript,
    KeyPair,
    ReplayError,
    SessionReplayState,
    SignatureVerificationError,
    StaleMessageError,
    decrypt_envelope,
    derive_session_keys,
    encrypt_envelope,
    generate_ed25519_keypair,
    generate_x25519_keypair,
    public_key_id,
    sign_transcript,
    verify_transcript_signature,
)
from security.crypto import (
    DEFAULT_ALGORITHM_SUITE,
    DEFAULT_PROTOCOL_VERSION,
    SecureEnvelope,
    encode_aad,
    nonce_for,
)

U96_MAX = 2**96 - 1


def _handshake() -> tuple[KeyPair, KeyPair, KeyPair, KeyPair, HandshakeTranscript]:
    server_signing = generate_ed25519_keypair()
    client_signing = generate_ed25519_keypair()
    server_eph = generate_x25519_keypair()
    client_eph = generate_x25519_keypair()
    transcript = HandshakeTranscript(
        protocol_version=DEFAULT_PROTOCOL_VERSION,
        role="frontend-backend",
        algorithm_suite=DEFAULT_ALGORITHM_SUITE,
        session_id="session-1",
        client_identity="frontend",
        server_identity="backend",
        client_key_id=public_key_id(client_signing.public_key),
        server_key_id=public_key_id(server_signing.public_key),
        server_ephemeral_pubkey=server_eph.public_key,
        client_ephemeral_pubkey=client_eph.public_key,
        timestamp_ms=1_800_000_000_000,
    )
    return server_signing, client_signing, server_eph, client_eph, transcript


def _derived_keys(
    client_eph: KeyPair | None = None,
    server_eph: KeyPair | None = None,
    transcript: HandshakeTranscript | None = None,
):
    _, _, se, ce, t = _handshake()
    client_eph = client_eph or ce
    server_eph = server_eph or se
    transcript = transcript or t
    return derive_session_keys(
        client_eph.private_key, server_eph.public_key, transcript
    )


def test_transcript_signature_verification_accepts_matching_transcript():
    server_signing, _, _, _, transcript = _handshake()
    signature = sign_transcript(server_signing.private_key, transcript)
    verify_transcript_signature(server_signing.public_key, transcript, signature)


def test_transcript_signature_verification_rejects_tampered_transcript():
    server_signing, _, _, _, transcript = _handshake()
    signature = sign_transcript(server_signing.private_key, transcript)
    tampered = replace(transcript, server_identity="iot-server")
    with pytest.raises(SignatureVerificationError):
        verify_transcript_signature(server_signing.public_key, tampered, signature)


def test_signature_rejects_tampered_every_field():
    server_signing, _, _, _, transcript = _handshake()
    signature = sign_transcript(server_signing.private_key, transcript)
    for field, value in [
        ("protocol_version", "OTHER/1"),
        ("role", "attacker-victim"),
        ("algorithm_suite", "RSA+MD5"),
        ("session_id", "different-session"),
        ("client_identity", "attacker"),
        ("server_identity", "different-server"),
        ("client_key_id", "deadbeef"),
        ("server_key_id", "cafebabe"),
        ("server_ephemeral_pubkey", b"\x01" * 32),
        ("client_ephemeral_pubkey", b"\x02" * 32),
        ("timestamp_ms", 0),
    ]:
        tampered = replace(transcript, **{field: value})
        with pytest.raises(SignatureVerificationError):
            verify_transcript_signature(server_signing.public_key, tampered, signature)


def test_transcript_signature_wrong_public_key():
    server_signing, client_signing, _, _, transcript = _handshake()
    signature = sign_transcript(server_signing.private_key, transcript)
    with pytest.raises(SignatureVerificationError):
        verify_transcript_signature(client_signing.public_key, transcript, signature)


def test_transcript_signature_tampered_signature_bytes():
    server_signing, _, _, _, transcript = _handshake()
    signature = sign_transcript(server_signing.private_key, transcript)
    with pytest.raises(SignatureVerificationError):
        verify_transcript_signature(
            server_signing.public_key, transcript, signature + b"\x00"
        )


class TestHandshakeTranscript:
    def test_digest_length(self):
        _, _, _, _, transcript = _handshake()
        assert len(transcript.digest()) == 32

    def test_encode_rejects_short_server_pubkey(self):
        _, _, _, _, transcript = _handshake()
        bad = replace(transcript, server_ephemeral_pubkey=b"\x00" * 31)
        with pytest.raises(AssertionError):
            bad.encode()

    def test_encode_rejects_long_server_pubkey(self):
        _, _, _, _, transcript = _handshake()
        bad = replace(transcript, server_ephemeral_pubkey=b"\x00" * 33)
        with pytest.raises(AssertionError):
            bad.encode()

    def test_encode_rejects_short_client_pubkey(self):
        _, _, _, _, transcript = _handshake()
        bad = replace(transcript, client_ephemeral_pubkey=b"\x00" * 31)
        with pytest.raises(AssertionError):
            bad.encode()

    def test_digest_different_for_different_transcripts(self):
        _, _, _, _, t = _handshake()
        t2 = replace(t, session_id="different-session")
        assert t.digest() != t2.digest()


class TestDeriveSessionKeys:
    def test_client_and_server_derive_identical_directional_keys(self):
        _, _, server_eph, client_eph, transcript = _handshake()
        server_keys = derive_session_keys(
            server_eph.private_key, client_eph.public_key, transcript
        )
        client_keys = derive_session_keys(
            client_eph.private_key, server_eph.public_key, transcript
        )
        assert server_keys == client_keys

    def test_client_write_key_is_32_bytes(self):
        keys = _derived_keys()
        assert len(keys.client_write_key) == 32

    def test_server_write_key_is_32_bytes(self):
        keys = _derived_keys()
        assert len(keys.server_write_key) == 32

    def test_client_nonce_base_is_12_bytes(self):
        keys = _derived_keys()
        assert len(keys.client_nonce_base) == 12

    def test_server_nonce_base_is_12_bytes(self):
        keys = _derived_keys()
        assert len(keys.server_nonce_base) == 12

    def test_client_and_server_keys_are_different(self):
        keys = _derived_keys()
        assert keys.client_write_key != keys.server_write_key

    def test_client_and_server_nonce_bases_are_different(self):
        keys = _derived_keys()
        assert keys.client_nonce_base != keys.server_nonce_base

    def test_deterministic_for_same_inputs(self):
        _, _, se, ce, t = _handshake()
        k1 = derive_session_keys(ce.private_key, se.public_key, t)
        k2 = derive_session_keys(ce.private_key, se.public_key, t)
        assert k1 == k2

    def test_different_transcript_different_keys(self):
        _, _, se, ce, t = _handshake()
        t2 = replace(t, session_id="session-2")
        k1 = derive_session_keys(ce.private_key, se.public_key, t)
        k2 = derive_session_keys(ce.private_key, se.public_key, t2)
        assert k1 != k2

    def test_different_info_different_keys(self):
        _, _, se, ce, t = _handshake()
        k1 = derive_session_keys(ce.private_key, se.public_key, t, info=b"info-a")
        k2 = derive_session_keys(ce.private_key, se.public_key, t, info=b"info-b")
        assert k1 != k2

    def test_rejects_short_private_key(self):
        _, _, se, ce, t = _handshake()
        with pytest.raises(AssertionError):
            derive_session_keys(b"\x00" * 31, ce.public_key, t)

    def test_rejects_short_public_key(self):
        _, _, se, ce, t = _handshake()
        with pytest.raises(AssertionError):
            derive_session_keys(ce.private_key, b"\x00" * 31, t)

    def test_write_key_selects_correct_direction(self):
        keys = _derived_keys()
        assert keys.write_key(Direction.CLIENT_TO_SERVER) == keys.client_write_key
        assert keys.write_key(Direction.SERVER_TO_CLIENT) == keys.server_write_key

    def test_nonce_base_selects_correct_direction(self):
        keys = _derived_keys()
        assert keys.nonce_base(Direction.CLIENT_TO_SERVER) == keys.client_nonce_base
        assert keys.nonce_base(Direction.SERVER_TO_CLIENT) == keys.server_nonce_base


class TestEncodeAad:
    def test_output_is_deterministic(self):
        aad1 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 1)
        aad2 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 1)
        assert aad1 == aad2

    def test_different_seq_different_aad(self):
        aad1 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 1)
        aad2 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 2)
        assert aad1 != aad2

    def test_different_direction_different_aad(self):
        aad1 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 1)
        aad2 = encode_aad("v1", "sid", Direction.SERVER_TO_CLIENT, 1)
        assert aad1 != aad2

    def test_different_session_different_aad(self):
        aad1 = encode_aad("v1", "sid-a", Direction.CLIENT_TO_SERVER, 1)
        aad2 = encode_aad("v1", "sid-b", Direction.CLIENT_TO_SERVER, 1)
        assert aad1 != aad2

    def test_includes_protocol_version(self):
        aad1 = encode_aad("v1", "sid", Direction.CLIENT_TO_SERVER, 1)
        aad2 = encode_aad("v2", "sid", Direction.CLIENT_TO_SERVER, 1)
        assert aad1 != aad2


class TestSecureEnvelope:
    def test_to_dict_roundtrip(self):
        env = SecureEnvelope(session_id="s1", seq=42, ciphertext="abc", tag="def")
        d = env.to_dict()
        assert d == {"session_id": "s1", "seq": 42, "ciphertext": "abc", "tag": "def"}
        restored = SecureEnvelope.from_dict(d)
        assert restored == env

    def test_from_dict_missing_session_id(self):
        with pytest.raises(DecodeError, match="session_id"):
            SecureEnvelope.from_dict({"seq": 0, "ciphertext": "a", "tag": "b"})

    def test_from_dict_missing_seq(self):
        with pytest.raises(DecodeError, match="seq"):
            SecureEnvelope.from_dict({"session_id": "s", "ciphertext": "a", "tag": "b"})

    def test_from_dict_missing_ciphertext(self):
        with pytest.raises(DecodeError, match="ciphertext"):
            SecureEnvelope.from_dict({"session_id": "s", "seq": 0, "tag": "b"})

    def test_from_dict_missing_tag(self):
        with pytest.raises(DecodeError, match="tag"):
            SecureEnvelope.from_dict({"session_id": "s", "seq": 0, "ciphertext": "a"})

    def test_from_dict_session_id_not_string(self):
        with pytest.raises(DecodeError, match="session_id must be a string"):
            SecureEnvelope.from_dict(
                {"session_id": 123, "seq": 0, "ciphertext": "a", "tag": "b"}
            )

    def test_from_dict_seq_not_int(self):
        with pytest.raises(DecodeError, match="seq must be an integer"):
            SecureEnvelope.from_dict(
                {"session_id": "s", "seq": "0", "ciphertext": "a", "tag": "b"}
            )

    def test_from_dict_seq_is_bool(self):
        with pytest.raises(DecodeError, match="seq must be an integer"):
            SecureEnvelope.from_dict(
                {"session_id": "s", "seq": True, "ciphertext": "a", "tag": "b"}
            )

    def test_from_dict_ciphertext_not_string(self):
        with pytest.raises(
            DecodeError, match="ciphertext and tag must be base64 strings"
        ):
            SecureEnvelope.from_dict(
                {"session_id": "s", "seq": 0, "ciphertext": 123, "tag": "b"}
            )

    def test_from_dict_tag_not_string(self):
        with pytest.raises(
            DecodeError, match="ciphertext and tag must be base64 strings"
        ):
            SecureEnvelope.from_dict(
                {"session_id": "s", "seq": 0, "ciphertext": "a", "tag": 456}
            )

    def test_from_dict_extra_fields_ignored(self):
        env = SecureEnvelope.from_dict(
            {"session_id": "s", "seq": 0, "ciphertext": "a", "tag": "b", "extra": "x"}
        )
        assert env.session_id == "s"
        assert env.seq == 0

    def test_from_dict_empty_dict(self):
        with pytest.raises(DecodeError):
            SecureEnvelope.from_dict({})


class TestEncryptDecrypt:
    def test_roundtrip(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"path": "/api/me", "payload": {"ok": True}},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        body = decrypt_envelope(
            envelope,
            keys,
            DEFAULT_PROTOCOL_VERSION,
            Direction.CLIENT_TO_SERVER,
            now_ms=1_800_000_000_002,
        )
        assert body["payload"] == {"ok": True}
        assert body["timestamp_ms"] == 1_800_000_000_001

    def test_roundtrip_server_to_client(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"result": "ok"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.SERVER_TO_CLIENT,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        body = decrypt_envelope(
            envelope,
            keys,
            DEFAULT_PROTOCOL_VERSION,
            Direction.SERVER_TO_CLIENT,
            now_ms=1_800_000_000_002,
        )
        assert body["result"] == "ok"

    def test_roundtrip_empty_body(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        body = decrypt_envelope(
            envelope,
            keys,
            DEFAULT_PROTOCOL_VERSION,
            Direction.CLIENT_TO_SERVER,
            now_ms=1_800_000_000_002,
        )
        assert "timestamp_ms" in body

    def test_default_timestamp_injected(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"data": "x"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
        )
        assert envelope.session_id == "s1"
        assert envelope.seq == 0

    def test_rejects_wrong_direction(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.SERVER_TO_CLIENT,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_stale_timestamp(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        with pytest.raises(StaleMessageError):
            decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_040_002,
            )

    def test_timestamp_exactly_at_skew_boundary(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "ok"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_000,
        )
        body = decrypt_envelope(
            envelope,
            keys,
            DEFAULT_PROTOCOL_VERSION,
            Direction.CLIENT_TO_SERVER,
            max_skew_ms=30_000,
            now_ms=1_800_000_030_000,
        )
        assert body["payload"] == "ok"

    def test_timestamp_one_ms_over_skew(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "ok"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_000,
        )
        with pytest.raises(StaleMessageError):
            decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                max_skew_ms=30_000,
                now_ms=1_800_000_030_001,
            )

    def test_rejects_wrong_session_id(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        wrong = replace(envelope, session_id="s2")
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                wrong,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_wrong_seq_in_aad(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        wrong = replace(envelope, seq=1)
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                wrong,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_tampered_ciphertext(self):
        from security.encoding import b64decode as bd
        from security.encoding import b64encode as be

        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        raw = bytearray(bd(envelope.ciphertext))
        raw[0] ^= 0xFF
        tampered = replace(envelope, ciphertext=be(bytes(raw)))
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                tampered,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_tampered_tag(self):
        from security.encoding import b64decode as bd
        from security.encoding import b64encode as be

        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        raw = bytearray(bd(envelope.tag))
        raw[0] ^= 0xFF
        tampered = replace(envelope, tag=be(bytes(raw)))
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                tampered,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_wrong_key(self):
        keys_a = _derived_keys()
        _, _, _, ce_b, t_b = _handshake()
        se_b = generate_x25519_keypair()
        keys_b = derive_session_keys(ce_b.private_key, se_b.public_key, t_b)
        envelope = encrypt_envelope(
            {"payload": "secret"},
            keys_a,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                envelope,
                keys_b,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_malformed_ciphertext_base64(self):
        keys = _derived_keys()
        envelope = SecureEnvelope(
            session_id="s1", seq=0, ciphertext="!!!invalid!!!", tag="AAAA"
        )
        with pytest.raises(DecodeError, match="invalid envelope base64"):
            decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_rejects_malformed_tag_base64(self):
        keys = _derived_keys()
        envelope = SecureEnvelope(
            session_id="s1", seq=0, ciphertext="AAAA", tag="!!!invalid!!!"
        )
        with pytest.raises(DecodeError, match="invalid envelope base64"):
            decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_different_seqs_produce_different_ciphertexts(self):
        keys = _derived_keys()
        e1 = encrypt_envelope(
            {"data": "same"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        e2 = encrypt_envelope(
            {"data": "same"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=1,
            now_ms=1_800_000_000_001,
        )
        assert e1.ciphertext != e2.ciphertext
        assert e1.tag != e2.tag

    def test_multiple_sequential_messages(self):
        keys = _derived_keys()
        for seq in range(10):
            envelope = encrypt_envelope(
                {"seq": seq},
                keys,
                DEFAULT_PROTOCOL_VERSION,
                "s1",
                Direction.CLIENT_TO_SERVER,
                seq=seq,
                now_ms=1_800_000_000_000 + seq,
            )
            body = decrypt_envelope(
                envelope,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_000 + seq + 1,
            )
            assert body["seq"] == seq

    def test_protocol_version_mismatch(self):
        keys = _derived_keys()
        envelope = encrypt_envelope(
            {"data": "x"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            "s1",
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_001,
        )
        with pytest.raises(DecryptionError):
            decrypt_envelope(
                envelope,
                keys,
                "WRONG-VERSION",
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )


class TestDecryptEdgeCases:
    def _encrypt_raw(
        self, keys, body: bytes, direction=Direction.CLIENT_TO_SERVER
    ) -> SecureEnvelope:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM

        nonce = nonce_for(keys.nonce_base(direction), 0)
        aad = encode_aad(DEFAULT_PROTOCOL_VERSION, "s1", direction, 0)
        encrypted = _AESGCM(keys.write_key(direction)).encrypt(nonce, body, aad)
        return SecureEnvelope(
            session_id="s1",
            seq=0,
            ciphertext=b64enc(encrypted[:-16]),
            tag=b64enc(encrypted[-16:]),
        )

    def test_missing_timestamp_in_body(self):
        keys = _derived_keys()
        env = self._encrypt_raw(keys, b'{"no_timestamp":true}')
        with pytest.raises(DecodeError, match="missing integer timestamp_ms"):
            decrypt_envelope(
                env,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_timestamp_is_bool(self):
        keys = _derived_keys()
        env = self._encrypt_raw(keys, b'{"timestamp_ms":true}')
        with pytest.raises(DecodeError, match="missing integer timestamp_ms"):
            decrypt_envelope(
                env,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_non_json_body(self):
        keys = _derived_keys()
        env = self._encrypt_raw(keys, b"not-json-at-all")
        with pytest.raises(DecodeError, match="decrypted body is not valid JSON"):
            decrypt_envelope(
                env,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_timestamp_is_float(self):
        keys = _derived_keys()
        env = self._encrypt_raw(keys, b'{"timestamp_ms":1.8e12}')
        with pytest.raises(DecodeError, match="missing integer timestamp_ms"):
            decrypt_envelope(
                env,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )

    def test_timestamp_is_string(self):
        keys = _derived_keys()
        env = self._encrypt_raw(keys, b'{"timestamp_ms":"now"}')
        with pytest.raises(DecodeError, match="missing integer timestamp_ms"):
            decrypt_envelope(
                env,
                keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_002,
            )


class TestReplayState:
    def test_requires_exact_next_sequence(self):
        state = SessionReplayState()
        direction = state.state_for(Direction.CLIENT_TO_SERVER)
        direction.accept_recv_seq(0)
        direction.accept_recv_seq(1)
        with pytest.raises(ReplayError):
            direction.accept_recv_seq(1)
        with pytest.raises(ReplayError):
            direction.accept_recv_seq(3)

    def test_check_recv_seq_does_not_advance(self):
        state = SessionReplayState()
        direction = state.state_for(Direction.CLIENT_TO_SERVER)
        direction.check_recv_seq(0)
        direction.check_recv_seq(0)
        direction.accept_recv_seq(0)
        assert direction.next_recv_seq == 1

    def test_rejects_older_seq(self):
        state = SessionReplayState()
        direction = state.state_for(Direction.CLIENT_TO_SERVER)
        direction.accept_recv_seq(0)
        direction.accept_recv_seq(1)
        direction.accept_recv_seq(2)
        with pytest.raises(ReplayError):
            direction.accept_recv_seq(1)
        with pytest.raises(ReplayError):
            direction.accept_recv_seq(0)

    def test_rejects_skipped_seq(self):
        state = SessionReplayState()
        direction = state.state_for(Direction.CLIENT_TO_SERVER)
        direction.accept_recv_seq(0)
        with pytest.raises(ReplayError):
            direction.accept_recv_seq(2)

    def test_allocate_send_seq_starts_at_zero(self):
        state = SessionReplayState()
        d = state.state_for(Direction.CLIENT_TO_SERVER)
        assert d.allocate_send_seq() == 0

    def test_allocate_send_seq_increments(self):
        state = SessionReplayState()
        d = state.state_for(Direction.CLIENT_TO_SERVER)
        assert d.allocate_send_seq() == 0
        assert d.allocate_send_seq() == 1
        assert d.allocate_send_seq() == 2

    def test_both_directions_independent_send(self):
        state = SessionReplayState()
        c = state.state_for(Direction.CLIENT_TO_SERVER)
        s = state.state_for(Direction.SERVER_TO_CLIENT)
        assert c.allocate_send_seq() == 0
        assert s.allocate_send_seq() == 0
        assert c.allocate_send_seq() == 1
        assert s.allocate_send_seq() == 1

    def test_both_directions_independent_recv(self):
        state = SessionReplayState()
        c = state.state_for(Direction.CLIENT_TO_SERVER)
        s = state.state_for(Direction.SERVER_TO_CLIENT)
        c.accept_recv_seq(0)
        s.accept_recv_seq(0)
        c.accept_recv_seq(1)
        s.accept_recv_seq(1)

    def test_receive_does_not_affect_send(self):
        state = SessionReplayState()
        d = state.state_for(Direction.CLIENT_TO_SERVER)
        d.accept_recv_seq(0)
        assert d.allocate_send_seq() == 0

    def test_send_does_not_affect_receive(self):
        state = SessionReplayState()
        d = state.state_for(Direction.CLIENT_TO_SERVER)
        d.allocate_send_seq()
        d.accept_recv_seq(0)

    def test_state_for_server_to_client(self):
        state = SessionReplayState()
        d = state.state_for(Direction.SERVER_TO_CLIENT)
        assert d.next_recv_seq == 0
        assert d.next_send_seq == 0


class TestFullSession:
    def test_multi_message_both_directions(self):
        server_signing, client_signing, server_eph, client_eph, transcript = (
            _handshake()
        )

        server_signature = sign_transcript(server_signing.private_key, transcript)
        verify_transcript_signature(
            server_signing.public_key, transcript, server_signature
        )

        client_keys = derive_session_keys(
            client_eph.private_key, server_eph.public_key, transcript
        )
        server_keys = derive_session_keys(
            server_eph.private_key, client_eph.public_key, transcript
        )
        assert client_keys == server_keys

        send_state = SessionReplayState()
        recv_state = SessionReplayState()

        now = 1_800_000_000_000
        for i in range(5):
            seq = send_state.state_for(Direction.CLIENT_TO_SERVER).allocate_send_seq()
            envelope = encrypt_envelope(
                {"msg": f"hello-{i}"},
                client_keys,
                DEFAULT_PROTOCOL_VERSION,
                transcript.session_id,
                Direction.CLIENT_TO_SERVER,
                seq=seq,
                now_ms=now,
            )
            recv_state.state_for(Direction.CLIENT_TO_SERVER).accept_recv_seq(
                envelope.seq
            )
            body = decrypt_envelope(
                envelope,
                server_keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=now + 1,
            )
            assert body["msg"] == f"hello-{i}"

        for i in range(3):
            seq = send_state.state_for(Direction.SERVER_TO_CLIENT).allocate_send_seq()
            envelope = encrypt_envelope(
                {"reply": f"resp-{i}"},
                server_keys,
                DEFAULT_PROTOCOL_VERSION,
                transcript.session_id,
                Direction.SERVER_TO_CLIENT,
                seq=seq,
                now_ms=now + 100,
            )
            recv_state.state_for(Direction.SERVER_TO_CLIENT).accept_recv_seq(
                envelope.seq
            )
            body = decrypt_envelope(
                envelope,
                client_keys,
                DEFAULT_PROTOCOL_VERSION,
                Direction.SERVER_TO_CLIENT,
                now_ms=now + 101,
            )
            assert body["reply"] == f"resp-{i}"

    def test_replay_attack_on_full_session_fails(self):
        _, _, server_eph, client_eph, transcript = _handshake()
        keys = derive_session_keys(
            client_eph.private_key, server_eph.public_key, transcript
        )
        state = SessionReplayState()
        direction = state.state_for(Direction.CLIENT_TO_SERVER)

        envelope = encrypt_envelope(
            {"msg": "first"},
            keys,
            DEFAULT_PROTOCOL_VERSION,
            transcript.session_id,
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_000,
        )
        direction.accept_recv_seq(0)
        decrypt_envelope(
            envelope,
            keys,
            DEFAULT_PROTOCOL_VERSION,
            Direction.CLIENT_TO_SERVER,
            now_ms=1_800_000_000_001,
        )

        with pytest.raises(ReplayError):
            direction.accept_recv_seq(0)

    def test_cross_session_replay_fails(self):
        _, _, se1, ce1, t1 = _handshake()
        _, _, se2, ce2, t2 = _handshake()
        keys1 = derive_session_keys(ce1.private_key, se1.public_key, t1)
        keys2 = derive_session_keys(ce2.private_key, se2.public_key, t2)

        envelope = encrypt_envelope(
            {"msg": "cross"},
            keys1,
            DEFAULT_PROTOCOL_VERSION,
            t1.session_id,
            Direction.CLIENT_TO_SERVER,
            seq=0,
            now_ms=1_800_000_000_000,
        )

        with pytest.raises(DecryptionError):
            decrypt_envelope(
                envelope,
                keys2,
                DEFAULT_PROTOCOL_VERSION,
                Direction.CLIENT_TO_SERVER,
                now_ms=1_800_000_000_001,
            )


def b64enc(data: bytes) -> str:
    from security.encoding import b64encode as _e

    return _e(data)
