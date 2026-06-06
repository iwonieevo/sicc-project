import { gcm } from "@noble/ciphers/aes.js";
import { ed25519, x25519 } from "@noble/curves/ed25519.js";
import { hkdf } from "@noble/hashes/hkdf.js";
import { sha256 } from "@noble/hashes/sha2.js";
import {
  b64decode,
  b64encode,
  concat,
  encodeU96,
  encodeUint64,
  encodeVar,
  fromUtf8,
  utf8,
} from "./encoding";

export const PROTOCOL_VERSION = "SICC-SECURE/1";
export const ALGORITHM_SUITE = "X25519+Ed25519+HKDF-SHA256+AES-256-GCM";
export const ROLE_FRONTEND_BACKEND = "frontend-backend";
export const CLIENT_TO_SERVER = "client->server";
export const SERVER_TO_CLIENT = "server->client";

const INFO = utf8("sicc secure transport v1");
const TAG_SIZE = 16;

export interface HandshakeTranscript {
  protocol_version: string;
  role: string;
  algorithm_suite: string;
  session_id: string;
  client_identity: string;
  server_identity: string;
  client_key_id: string;
  server_key_id: string;
  server_ephemeral_pubkey: Uint8Array;
  client_ephemeral_pubkey: Uint8Array;
  timestamp_ms: number;
}

export interface DerivedKeys {
  clientWriteKey: Uint8Array;
  serverWriteKey: Uint8Array;
  clientNonceBase: Uint8Array;
  serverNonceBase: Uint8Array;
}

export interface SecureEnvelope {
  session_id: string;
  seq: number;
  ciphertext: string;
  tag: string;
}

export interface X25519KeyPair {
  secretKey: Uint8Array;
  publicKey: Uint8Array;
}

export function generateX25519KeyPair(): X25519KeyPair {
  return x25519.keygen();
}

export function encodeTranscript(transcript: HandshakeTranscript): Uint8Array {
  requireLength("server_ephemeral_pubkey", transcript.server_ephemeral_pubkey, 32);
  requireLength("client_ephemeral_pubkey", transcript.client_ephemeral_pubkey, 32);
  return concat([
    encodeVar(transcript.protocol_version),
    encodeVar(transcript.role),
    encodeVar(transcript.algorithm_suite),
    encodeVar(transcript.session_id),
    encodeVar(transcript.client_identity),
    encodeVar(transcript.server_identity),
    encodeVar(transcript.client_key_id),
    encodeVar(transcript.server_key_id),
    transcript.server_ephemeral_pubkey,
    transcript.client_ephemeral_pubkey,
    encodeUint64(transcript.timestamp_ms),
  ]);
}

export function verifyTranscriptSignature(
  publicKey: Uint8Array,
  transcript: HandshakeTranscript,
  signature: Uint8Array,
): void {
  requireLength("publicKey", publicKey, 32);
  if (!ed25519.verify(signature, encodeTranscript(transcript), publicKey, { zip215: false })) {
    throw new Error("invalid backend transcript signature");
  }
}

export function deriveSessionKeys(
  ownEphemeralSecretKey: Uint8Array,
  peerEphemeralPublicKey: Uint8Array,
  transcript: HandshakeTranscript,
): DerivedKeys {
  const sharedSecret = x25519.getSharedSecret(ownEphemeralSecretKey, peerEphemeralPublicKey);
  const material = hkdf(sha256, sharedSecret, sha256(encodeTranscript(transcript)), INFO, 88);
  return {
    clientWriteKey: material.slice(0, 32),
    serverWriteKey: material.slice(32, 64),
    clientNonceBase: material.slice(64, 76),
    serverNonceBase: material.slice(76, 88),
  };
}

export function publicKeyId(publicKey: Uint8Array): string {
  requireLength("publicKey", publicKey, 32);
  return b64encode(sha256(publicKey).slice(0, 16));
}

export function encryptEnvelope(
  body: Record<string, unknown>,
  keys: DerivedKeys,
  protocolVersion: string,
  sessionId: string,
  direction: typeof CLIENT_TO_SERVER | typeof SERVER_TO_CLIENT,
  seq: number,
): SecureEnvelope {
  const bodyWithTimestamp = {
    ...body,
    timestamp_ms: Date.now(),
  };
  const plaintext = utf8(stableStringify(bodyWithTimestamp));
  const cipher = gcm(
    writeKey(keys, direction),
    nonceFor(nonceBase(keys, direction), seq),
    encodeAad(protocolVersion, sessionId, direction, seq),
  );
  const encrypted = cipher.encrypt(plaintext);
  return {
    session_id: sessionId,
    seq,
    ciphertext: b64encode(encrypted.slice(0, encrypted.length - TAG_SIZE)),
    tag: b64encode(encrypted.slice(encrypted.length - TAG_SIZE)),
  };
}

export function decryptEnvelope(
  envelope: SecureEnvelope,
  keys: DerivedKeys,
  protocolVersion: string,
  direction: typeof CLIENT_TO_SERVER | typeof SERVER_TO_CLIENT,
  maxSkewMs: number,
): Record<string, unknown> {
  const encrypted = concat([b64decode(envelope.ciphertext), b64decode(envelope.tag)]);
  const cipher = gcm(
    writeKey(keys, direction),
    nonceFor(nonceBase(keys, direction), envelope.seq),
    encodeAad(protocolVersion, envelope.session_id, direction, envelope.seq),
  );
  const plaintext = cipher.decrypt(encrypted);
  const body = JSON.parse(fromUtf8(plaintext));
  if (typeof body !== "object" || body === null || !Number.isInteger(body.timestamp_ms)) {
    throw new Error("decrypted body is missing integer timestamp_ms");
  }
  if (Date.now() - body.timestamp_ms > maxSkewMs) {
    throw new Error("message timestamp is too old");
  }
  return body;
}

function encodeAad(
  protocolVersion: string,
  sessionId: string,
  direction: string,
  seq: number,
): Uint8Array {
  return concat([
    encodeVar(protocolVersion),
    encodeVar(sessionId),
    encodeVar(direction),
    encodeU96(seq),
  ]);
}

function nonceFor(base: Uint8Array, seq: number): Uint8Array {
  requireLength("nonceBase", base, 12);
  const seqBytes = encodeU96(seq);
  return base.map((value, index) => value ^ seqBytes[index]);
}

function writeKey(
  keys: DerivedKeys,
  direction: typeof CLIENT_TO_SERVER | typeof SERVER_TO_CLIENT,
): Uint8Array {
  return direction === CLIENT_TO_SERVER ? keys.clientWriteKey : keys.serverWriteKey;
}

function nonceBase(
  keys: DerivedKeys,
  direction: typeof CLIENT_TO_SERVER | typeof SERVER_TO_CLIENT,
): Uint8Array {
  return direction === CLIENT_TO_SERVER ? keys.clientNonceBase : keys.serverNonceBase;
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(object[key])}`)
    .join(",")}}`;
}

function requireLength(name: string, value: Uint8Array, expected: number): void {
  if (value.length !== expected) {
    throw new Error(`${name} must be ${expected} bytes`);
  }
}
