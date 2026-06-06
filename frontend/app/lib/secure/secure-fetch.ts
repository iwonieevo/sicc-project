import {
  ALGORITHM_SUITE,
  CLIENT_TO_SERVER,
  PROTOCOL_VERSION,
  ROLE_FRONTEND_BACKEND,
  SERVER_TO_CLIENT,
  decryptEnvelope,
  deriveSessionKeys,
  encryptEnvelope,
  generateX25519KeyPair,
  publicKeyId,
  verifyTranscriptSignature,
  type DerivedKeys,
  type HandshakeTranscript,
  type SecureEnvelope,
} from "./crypto";
import { b64decode, b64encode } from "./encoding";

const CLIENT_IDENTITY = "browser";
const CLIENT_KEY_ID = "anonymous";
const TOFU_STORAGE_KEY = "sicc.backendPublicKey";

interface SecureConfig {
  secure_mode: boolean;
  protocol_version: string;
  algorithm_suite: string;
  server_identity: string;
  server_key_id: string | null;
  server_public_key: string | null;
  max_skew_ms: number;
  tofu_allowed: boolean;
}

interface HandshakeResponse {
  protocol_version: string;
  algorithm_suite: string;
  role: string;
  session_id: string;
  client_identity: string;
  server_identity: string;
  client_key_id: string;
  server_key_id: string;
  server_ephemeral_pubkey: string;
  client_ephemeral_pubkey: string;
  timestamp_ms: number;
  server_signature: string;
}

interface SecureSession {
  sessionId: string;
  protocolVersion: string;
  keys: DerivedKeys;
  maxSkewMs: number;
  sendSeq: number;
  recvSeq: number;
}

export interface SecureFetchResponse {
  ok: boolean;
  status: number;
  json: <T = unknown>() => Promise<T>;
  text: () => Promise<string>;
}

let session: SecureSession | null = null;
let handshakePromise: Promise<SecureSession> | null = null;
let configPromise: Promise<SecureConfig> | null = null;
let requestQueue: Promise<unknown> = Promise.resolve();

export function clearSecureTransportSession(): void {
  session = null;
  handshakePromise = null;
  configPromise = null;
  requestQueue = Promise.resolve();
}

async function getOrLoadConfig(): Promise<SecureConfig> {
  if (configPromise === null) {
    const response = await fetch("/api/secure/frontend-backend/config", {
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error("secure transport config unavailable");
    }
    configPromise = response.json();
  }
  return configPromise;
}

export async function secureFetch(
  input: string,
  init: RequestInit = {},
): Promise<SecureFetchResponse> {
  const config = await getOrLoadConfig();
  if (!config.secure_mode) {
    return fetch(input, init);
  }

  const run = () => secureFetchLocked(input, init, config);
  const result = requestQueue.then(run, run);
  requestQueue = result.catch(() => undefined);
  return result;
}

async function secureFetchLocked(
  input: string,
  init: RequestInit,
  config: SecureConfig,
): Promise<SecureFetchResponse> {
  const activeSession = await getOrCreateSession(config);
  const request = buildEncryptedRequest(input, init);
  const envelope = encryptEnvelope(
    request,
    activeSession.keys,
    activeSession.protocolVersion,
    activeSession.sessionId,
    CLIENT_TO_SERVER,
    activeSession.sendSeq,
  );
  activeSession.sendSeq += 1;

  const response = await fetch("/api/secure/frontend-backend/request", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(envelope),
  });
  if (!response.ok) {
    clearSecureTransportSession();
    throw new Error("secure transport failed");
  }

  const responseEnvelope = (await response.json()) as SecureEnvelope;
  if (responseEnvelope.seq !== activeSession.recvSeq) {
    clearSecureTransportSession();
    throw new Error("secure response sequence mismatch");
  }
  activeSession.recvSeq += 1;

  const responseBody = decryptEnvelope(
    responseEnvelope,
    activeSession.keys,
    activeSession.protocolVersion,
    SERVER_TO_CLIENT,
    activeSession.maxSkewMs,
  );
  const statusCode = responseBody.status_code;
  if (!Number.isInteger(statusCode)) {
    throw new Error("secure response missing status_code");
  }
  return responseFromBody(statusCode as number, responseBody.body);
}

async function getOrCreateSession(config: SecureConfig): Promise<SecureSession> {
  if (session) {
    return session;
  }
  if (!handshakePromise) {
    handshakePromise = createSession(config).then((created) => {
      session = created;
      handshakePromise = null;
      return created;
    });
  }
  return handshakePromise;
}

async function createSession(config: SecureConfig): Promise<SecureSession> {
  validateConfig(config);
  const serverPublicKey = selectTrustedServerPublicKey(config);
  const serverKeyId = config.server_key_id as string;
  const serverIdentity = config.server_identity;
  const keyPair = generateX25519KeyPair();
  const start = {
    role: ROLE_FRONTEND_BACKEND,
    session_id: crypto.randomUUID(),
    client_identity: CLIENT_IDENTITY,
    server_identity: serverIdentity,
    client_key_id: CLIENT_KEY_ID,
    server_key_id: serverKeyId,
    client_ephemeral_pubkey: b64encode(keyPair.publicKey),
    timestamp_ms: Date.now(),
  };

  const response = await fetch("/api/secure/frontend-backend/handshake/start", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(start),
  });
  if (!response.ok) {
    throw new Error("secure handshake failed");
  }
  const data = (await response.json()) as HandshakeResponse;
  validateHandshakeEcho(start, data, config);

  const transcript: HandshakeTranscript = {
    protocol_version: data.protocol_version,
    role: data.role,
    algorithm_suite: data.algorithm_suite,
    session_id: data.session_id,
    client_identity: data.client_identity,
    server_identity: data.server_identity,
    client_key_id: data.client_key_id,
    server_key_id: data.server_key_id,
    server_ephemeral_pubkey: b64decode(data.server_ephemeral_pubkey),
    client_ephemeral_pubkey: b64decode(data.client_ephemeral_pubkey),
    timestamp_ms: data.timestamp_ms,
  };
  verifyTranscriptSignature(serverPublicKey, transcript, b64decode(data.server_signature));

  return {
    sessionId: data.session_id,
    protocolVersion: data.protocol_version,
    keys: deriveSessionKeys(keyPair.secretKey, transcript.server_ephemeral_pubkey, transcript),
    maxSkewMs: config.max_skew_ms,
    sendSeq: 0,
    recvSeq: 0,
  };
}

function validateConfig(config: SecureConfig): void {
  if (config.protocol_version !== PROTOCOL_VERSION) {
    throw new Error("unsupported secure protocol version");
  }
  if (config.algorithm_suite !== ALGORITHM_SUITE) {
    throw new Error("unsupported secure algorithm suite");
  }
  if (!config.server_key_id || !config.server_public_key) {
    throw new Error("backend secure identity is not configured");
  }
}

function selectTrustedServerPublicKey(config: SecureConfig): Uint8Array {
  const pinnedKey = import.meta.env.VITE_SICC_BACKEND_PUBLIC_KEY_B64 as string | undefined;
  const pinnedKeyId = import.meta.env.VITE_SICC_BACKEND_KEY_ID as string | undefined;
  const pinnedIdentity = import.meta.env.VITE_SICC_BACKEND_IDENTITY as string | undefined;

  if (pinnedIdentity && pinnedIdentity !== config.server_identity) {
    throw new Error("pinned backend identity mismatch");
  }
  if (pinnedKeyId && pinnedKeyId !== config.server_key_id) {
    throw new Error("pinned backend key id mismatch");
  }
  if (pinnedKey) {
    const key = b64decode(pinnedKey);
    if (publicKeyId(key) !== config.server_key_id) {
      throw new Error("pinned backend public key id mismatch");
    }
    return key;
  }

  if (!config.tofu_allowed || !config.server_public_key) {
    throw new Error("backend public key is not pinned and TOFU is disabled");
  }

  const offered = {
    identity: config.server_identity,
    key_id: config.server_key_id,
    public_key: config.server_public_key,
  };
  const stored = localStorage.getItem(TOFU_STORAGE_KEY);
  if (!stored) {
    localStorage.setItem(TOFU_STORAGE_KEY, JSON.stringify(offered));
    return b64decode(config.server_public_key);
  }

  const trusted = JSON.parse(stored);
  if (
    trusted.identity !== offered.identity ||
    trusted.key_id !== offered.key_id ||
    trusted.public_key !== offered.public_key
  ) {
    throw new Error("backend TOFU public key changed");
  }
  return b64decode(trusted.public_key);
}

function validateHandshakeEcho(
  start: Record<string, unknown>,
  data: HandshakeResponse,
  config: SecureConfig,
): void {
  const expected = {
    ...start,
    protocol_version: config.protocol_version,
    algorithm_suite: config.algorithm_suite,
  };
  for (const [key, value] of Object.entries(expected)) {
    if ((data as unknown as Record<string, unknown>)[key] !== value) {
      throw new Error(`handshake response field mismatch: ${key}`);
    }
  }
}

function buildEncryptedRequest(input: string, init: RequestInit): Record<string, unknown> {
  const url = new URL(input, window.location.origin);
  const params = Object.fromEntries(url.searchParams.entries());
  const headers = new Headers(init.headers);
  const json = parseJsonBody(init.body);
  return {
    method: (init.method || "GET").toUpperCase(),
    path: url.pathname,
    json,
    params: Object.keys(params).length > 0 ? params : null,
    headers: Object.fromEntries(
      Array.from(headers.entries()).filter(([key]) =>
        ["authorization", "content-type"].includes(key.toLowerCase()),
      ),
    ),
  };
}

function parseJsonBody(body: BodyInit | null | undefined): Record<string, unknown> | null {
  if (body == null) {
    return null;
  }
  if (typeof body !== "string") {
    throw new Error("secure fetch only supports JSON string bodies");
  }
  const parsed = JSON.parse(body);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("secure fetch JSON body must be an object");
  }
  return parsed as Record<string, unknown>;
}

function responseFromBody(status: number, body: unknown): SecureFetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async <T = unknown>() => body as T,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body ?? null)),
  };
}
