const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

export function utf8(value: string): Uint8Array {
  return textEncoder.encode(value);
}

export function fromUtf8(value: Uint8Array): string {
  return textDecoder.decode(value);
}

export function encodeVar(value: string): Uint8Array {
  const data = utf8(value);
  if (data.length > 0xffff) {
    throw new Error("variable field exceeds 65535 bytes");
  }
  return concat([new Uint8Array([data.length >> 8, data.length & 0xff]), data]);
}

export function encodeUint64(value: number): Uint8Array {
  return encodeBigEndian(BigInt(value), 8);
}

export function encodeU96(value: number): Uint8Array {
  return encodeBigEndian(BigInt(value), 12);
}

export function concat(parts: Uint8Array[]): Uint8Array {
  const length = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

export function b64encode(data: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < data.length; index += 1) {
    binary += String.fromCharCode(data[index]);
  }
  return btoa(binary);
}

export function b64decode(value: string): Uint8Array {
  const binary = atob(value);
  const output = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    output[index] = binary.charCodeAt(index);
  }
  return output;
}

function encodeBigEndian(value: bigint, size: number): Uint8Array {
  if (value < 0n || value >= 1n << BigInt(size * 8)) {
    throw new Error("integer out of range");
  }
  const output = new Uint8Array(size);
  let cursor = value;
  for (let index = size - 1; index >= 0; index -= 1) {
    output[index] = Number(cursor & 0xffn);
    cursor >>= 8n;
  }
  return output;
}
