from __future__ import annotations

import base64
import struct
from collections.abc import Iterable


UINT16_MAX = 2**16 - 1
UINT64_MAX = 2**64 - 1
U96_MAX = 2**96 - 1


def encode_var(value: str) -> bytes:
    data = value.encode("utf-8")
    if len(data) > UINT16_MAX:
        raise ValueError("variable field exceeds 65535 bytes")
    return struct.pack(">H", len(data)) + data


def encode_uint64(value: int) -> bytes:
    if not 0 <= value <= UINT64_MAX:
        raise ValueError("uint64 value out of range")
    return value.to_bytes(8, "big")


def encode_u96(value: int) -> bytes:
    if not 0 <= value <= U96_MAX:
        raise ValueError("96-bit integer out of range")
    return value.to_bytes(12, "big")


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def concat(parts: Iterable[bytes]) -> bytes:
    return b"".join(parts)
