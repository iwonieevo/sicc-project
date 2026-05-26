# Overview

The two core assumptions of this project are:

1. All requests go through HTTP, not HTTPS,
2. We are working with incredibly sensitive data that must not be leaked.

This document describes the security measures applied at every layer of the system to ensure data confidentiality and integrity. We also consider the possibility that one of our own members might be compromised. We assume the host of the operating system of the backend server is secure. We do not, however, assume that the bad actor is in possession of a quantum computer.

## Authorization

User entries are stored in the database in a table with following columns:

- `id` - A random UUIDv4
- `username` - Plaintext username
- `password` - The hashed password of the username. Computed with argon2id
- `last_seen` - A timezoned timestamp. Updated whenever the user performs any action from their account.
- `created_at` - Assigned once, at the creation of the account

## Sessions

The primary web-based authentication method is done through short-lived (15-minute) JWT, signed with EdDSA. Refresh tokens are valid for 7 days, stored exclusively as `httpOnly` cookies. On every use, the refresh token is invalidated and a new one is issued.

## 2FA

Accounts are additionally protected by two-factor authentication with a time-based one-time password (RFC 6238 standard). Supported through every authenticator app (Google, Microsoft, Ente, etc.) Generated as a base32 secret, and shown to the user as a QR code generated during account setup - every subsequent login requires a valid code after the password. The secret as well as the backup codes are then encrypted with a dedicated key and stored in the database.

# Encryption

Inspired by TLS, SICC uses a hybrid encryption model:

1. We first perform a key exchange (X25519). Keys are ephemeral and per-session only - past sessions remain safe even if the current key is compromised.
2. Symmetric encryption with AES-256-GCM. GCM mode provides both encryption and authentication, so any tampering with the ciphertext causes decryption to fail.

## Server Identity Verification

Considering we operate on HTTP and cannot rely on HTTPS certificates for server verification, we deploy our own system: An Ed25519 keypair is generated before running any of the applications. The backend receives the private key (stored in .env - as mentioned before, we assume the host is perfectly secure), whereas the Raspberry Pi devices and frontend receive only the public keys.

During the handshake, the ephemeral public key is signed with its long-term Ed25519 private key. The client receives a payload of format `[public key] + [signature]`. Following that, each client (frontend/raspberry pi) can independently verify the signature with its Ed25519 public key. If the signature is invalid, then it is likely that someone is attempting a MitM attack. Obviously, such connection must be dropped at that point.

Because initial delivery over HTTP is inherently vulnerable, we assume the frontend application (and its bundled server public key) is distributed securely out-of-band, or we rely on Trust On First Use (TOFU).

## Raspberry Pi Identity Verification

Similar to the Server Identity Verification mechanism, each RPi has its own Ed25519 keypair generated prior to deployment. The private key is stored in the RPi's `.env`, and the corresponding public key is registered in the backend's device registry. On each request, the RPi signs its ephemeral X25519 public key with its long-term Ed25519 private key, mirroring the frontend<->backend handshake. The backend verifies the signature against the registered public key.

# Attack prevention

Every encrypted payload contains the following fields:

- Random nonce (12 bytes)
- Unix timestamp (in ms)
- Unique request ID

We reject everything older than 30 seconds, and maintains a short-lived cache of recent request IDs to block exact replays within that window.

As keys are ephemeral per session, random 96-bit nonces are safe from collision within this bound.

# Database

As mentioned before, passwords and TOTP secrets are never stored in plaintext. Sensitive columns (for instance, execution results) are encrypted at column level with AES-256-GCM with appropriate keys.

Database connections use TLS with a local self-signed CA. PostgreSQL presents a server certificate signed by this CA, and backend services verify it with `sslmode=verify-full`.

# Logs

As mentioned, we take additional precautions against even ourselves to ensure logs cannot be tampered with. A compromised admin could otherwise silently modify or delete plaintext audit log entries. All audit log entries are therefore hash-chained, making tampering mathematically detectable:

```
[1] = { data, hash: HMAC-SHA256(key, data) },
[2] = { data, hash: HMAC-SHA256(key, data | prev_hash) }
[3] = { data, hash: HMAC-SHA256(key, data | prev_hash) }
```

Editing any entry breaks every hash that follows it.

# Flagging Malicious Activity

- Every authentication-related user event is logged: Auth Success, Auth Fail, 2FA attempts, Token Refresh.
- Requests are rate-limited per IP + per username - we deploy an exponential backoff after 5 consecutive failures
- Bad requests (repeated nonces, failed signature verification, failed decryption) are all flagged and logged.

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
