# Overview

The two core assumptions of this project are:

1. All requests go through HTTP, not HTTPS,
2. We are working with incredibly sensitive data that must not be leaked.

This document describes the security measures applied at every layer of the system to ensure data confidentiality and integrity. We also consider the possibility that one of our own members might be compromised. We assume the host of the operating system of the backend server is secure. We do not, however, assume that the bad actor is in possession of a quantum computer.

## Authorization

User entries are stored in the database in a table with following columns:

- `id` - An auto-incremented integer primary key
- `username` - Plaintext username
- `hashed_password` - The hashed password of the username. Computed with argon2id
- `last_seen` - A timezoned timestamp. Updated whenever the user performs any action from their account.
- `created_at` - Assigned once, at the creation of the account
- `is_deleted` - Soft-delete flag

## Sessions

The primary web-based authentication method is done through short-lived (15-minute) JWT, signed with EdDSA. Refresh tokens are valid for 7 days, stored exclusively as `httpOnly` cookies. On every use, the refresh token is invalidated and a new one is issued.

# Encryption

Inspired by TLS, SICC uses a hybrid encryption model:

1. We first perform a key exchange (X25519). Keys are ephemeral and per-session only - past sessions remain safe even if the current key is compromised.
2. Symmetric encryption with AES-256-GCM. GCM mode provides both encryption and authentication, so any tampering with the ciphertext causes decryption to fail.

## Handshake and Key Derivation

The handshake transcript binds all negotiated parameters before any keys are derived. The transcript is defined as the concatenation of:
`protocol_version || role || algorithm_suite || session_id || client_identity || server_identity || client_key_id || server_key_id || server_ephemeral_pubkey || client_ephemeral_pubkey || timestamp_ms`

`client_identity` and `server_identity` are the logical names of the two parties (e.g. "frontend", "backend", "iot-server", or a device ID for RPi agents). `client_key_id` and `server_key_id` identify which long-term Ed25519 keypair each party is using, allowing the receiver to unambiguously look up the correct registered public key before verification.

Concatenation is only unambiguous when field boundaries cannot shift. All transcript and AAD fields are encoded using one of two forms:

- Fixed-size binary fields (keys, nonces, timestamps): written as raw bytes of their
  defined length with no prefix.
- Variable-length fields (identity strings, algorithm suite, protocol version): encoded
  as a 2-byte big-endian length prefix followed by the UTF-8 bytes of the value.

The X25519 shared secret is never used directly as an encryption key. Instead, HKDF (SHA-256) is applied over the shared secret and the SHA-256 hash of the full transcript:

```
ikm  = X25519(server_ephemeral_priv, client_ephemeral_pub)
salt = SHA256(transcript)
keys = HKDF-Expand(HKDF-Extract(salt, ikm), info, length=88)

client_write_key = keys[0:32]   # AES-256-GCM, client -> server
server_write_key = keys[32:64]  # AES-256-GCM, server -> client
client_nonce_base = keys[64:76] # 96-bit nonce base, client -> server
server_nonce_base = keys[76:88] # 96-bit nonce base, server -> client
```

Separate keys per direction prevent reflection attacks and eliminate nonce-space overlap between directions.

Nonces are constructed as `nonce_base XOR seq` where `seq` is the per-direction sequence 96-bit big-endian integer (see Replay Prevention).

## Server Identity Verification

Each service in the system has its own long-term Ed25519 keypair generated prior to deployment. The backend and the IoT server are distinct services with distinct identities and do not share a private key. Every service stores its private key in its own `.env` (the host is assumed secure). Counterparties hold only the relevant public keys:

- The frontend holds the backend's public key.
- The backend holds the IoT server's public key (and vice versa).
- The IoT server holds each registered RPi's public key.

During the handshake, the server-role party signs the full handshake transcript (defined above) with its long-term Ed25519 private key. The client receives the server's ephemeral public key alongside this signature and can independently verify it against the known public key for that service identity (`server_key_id` from the transcript). A failed signature verification indicates a likely MitM attack and the connection must be dropped immediately.

For browser-to-backend traffic, the frontend uses a server-authenticated ECDHE variant. The browser generates only an ephemeral X25519 key for the current in-memory transport session instaed of keeping a registered long-term Ed25519 identity. The backend signs the transcript with its long-term Ed25519 key, the browser verifies that signature using the pinned or TOFU backend public key, and normal user authentication happens inside the encrypted transport.

## Trust On First Use (TOFU)

Because the initial delivery of the frontend application (and its bundled server public key) occurs over plain HTTP, it is inherently vulnerable on first load. An attacker capable of intercepting that first request could substitute both the JavaScript bundle and the embedded public key before the crypto layer has any chance to run.
This is a known and accepted limitation of the threat model. We mitigate it by assuming the frontend bundle is distributed securely out-of-band where possible. For cases relying on TOFU, the first connection is a weak point and is explicitly not claimed to provide the same guarantees as subsequent connections. Any deployment where first-load security is critical must use out-of-band key distribution.

## Raspberry Pi Identity Verification

Each RPi agent has their own enrollment token, service identity, and a pair of Ed25519 keys for secure transport. The enrollment token payload contains a version, issuer, agent_id, public_key_id, unique jti, issued-at timestamp, expiry timestamp, and an HMAC signature created with the enrollment secret. Binding the token to the generated public_key_id prevents a captured token from being reused to register a different agent key. The `scripts/agents.py` wrapper generates the token and keypair together.

In secure mode, the agent first opens a server-authenticated `agent-enrollment` session using its pinned IoT server public key - similar to how frontend<->backend handshakes are made, then sends the enrollment token and generated public key inside the encrypted channel.

After registration, the corresponding public key is registered in the device registry. On each secure session initiation, the RPi signs the full handshake transcript with its long-term Ed25519 private key. Any device whose public key is not in the shared device registry is rejected outright.

# Attack prevention

## Envelope Format

```json
{
  "session_id": "...",
  "seq": 42,
  "ciphertext": "base64...",
  "tag": "base64..."
}
```

The actual request body, including all sensitive fields, lives inside ciphertext.

## Additional Authenticated Data (AAD)

The AAD field passed to AES-GCM on every message is:

```
protocol_version || session_id || direction || seq_as_96bit_big_endian
```

## Replay Prevention

Each direction of each session maintains a monotonically increasing sequence number (`seq`), starting at 0 and incremented by 1 per message. The sequence number is
cryptographically bound to the ciphertext via AAD (see above) without being encrypted.

The receiver requires the incoming `seq` to be exactly equal to the next expected sequence number for that session and direction, and rejects anything else. This is stricter than "strictly greater than last seen" and eliminates any ambiguity around gaps or skipped messages. This design requires encrypted messages to be processed in strict send order per session.

A timestamp (big-endian Unix milliseconds) is also included inside the encrypted envelope as a secondary sanity check. Messages timestamped more than 30 seconds in the past are rejected even if the sequence number would otherwise be valid.

# Database

Database connections use TLS with a local self-signed CA. PostgreSQL presents a server certificate signed by this CA, and backend services verify it with `sslmode=verify-full`.

# Flagging Malicious Activity

- Every authentication-related user event is logged: Auth Success, Auth Fail, Token Refresh.
- Bad requests (replay attempts, failed signature verification, failed decryption) are all flagged and logged.

# Additional Precautions

1. Tokens are stored as `httpOnly`, never `localStorage`.
2. CSRF tokens are required on cookie-reliant endpoints (token refresh).
3. CORS headers locked to the exact frontend origin.
4. All user input and server output is strictly sanitized before rendering.
5. Security headers are set on all responses:

```
X-Frame-Options: DENY             # protects against "clickjacking"
X-Content-Type-Options: nosniff   # protects against MIME confusion attacks
Referrer-Policy: no-referrer      # protects against potential data leakage
Content-Security-Policy: <policy> # a strict allowlist for the website, a good XSS precaution
```

6. Failed authentication return a generic error message, not a specialized one - "invalid credentials" over "this username already exists" to prevent enumeration attacks.
7. Any manual comparisons on the backend must be done with cryptographically secure functions to prevent timing attacks.
8. Never reimplement cryptographic algorithms. Use only well established, audited dependencies.
9. Keys are NEVER comitted to version control and are kept in `.env` instead.

# Plaintext Mode

To satisfy the project's requirements, an environment flag `SECURE_MODE` is used to determine whether the security systems should be enabled. If set to `false`, we communicate with no security measures, basically through plaintext.
