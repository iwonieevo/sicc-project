from __future__ import annotations

import hashlib
import os
import re
import time

from fastapi import HTTPException, Request, status
from valkey import Valkey, ValkeyError

_client: Valkey | None = None


def _get_client() -> Valkey:
    global _client
    if _client is None:
        url = os.getenv("SICC_VALKEY_URL")
        if not url:
            raise RuntimeError("SICC_VALKEY_URL is required for rate limiting")
        _client = Valkey.from_url(url, decode_responses=True)
    return _client


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rate_limit_key(bucket: str, identifier: str, window_seconds: int) -> str:
    window = int(time.time()) // window_seconds
    return f"rate-limit:{bucket}:{window}:{_stable_hash(identifier)}"


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    if limit <= 0 or window_seconds <= 0:
        raise RuntimeError("Rate limit and window must be positive integers")

    key = _rate_limit_key(bucket, identifier, window_seconds)
    try:
        client = _get_client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        if int(count) > limit:
            ttl = client.ttl(key)
            retry_after = str(ttl if isinstance(ttl, int) and ttl > 0 else window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": retry_after},
            )
    except HTTPException:
        raise
    except (RuntimeError, ValkeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting is unavailable",
        ) from exc


def enforce_auth_rate_limit(
    request: Request,
    *,
    action: str,
    account_identifier: str | None = None,
) -> None:
    ip = _client_ip(request)
    ip_limit = int(os.getenv(f"SICC_{action.upper()}_IP_RATE_LIMIT", "20"))
    account_limit = int(os.getenv(f"SICC_{action.upper()}_ACCOUNT_RATE_LIMIT", "10"))
    window_seconds = int(os.getenv(f"SICC_{action.upper()}_RATE_LIMIT_WINDOW_SECONDS", "300"))

    enforce_rate_limit(
        request,
        bucket=f"auth:{action}:ip",
        identifier=ip,
        limit=ip_limit,
        window_seconds=window_seconds,
    )

    if account_identifier:
        enforce_rate_limit(
            request,
            bucket=f"auth:{action}:account",
            identifier=account_identifier.lower(),
            limit=account_limit,
            window_seconds=window_seconds,
        )


def _env_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def enforce_frontend_route_rate_limit(
    *,
    route: str,
    user_email: str,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> None:
    route_key = _env_key(route)
    route_limit = limit or int(
        os.getenv(f"SICC_ROUTE_{route_key}_RATE_LIMIT", os.getenv("SICC_ROUTE_RATE_LIMIT", "120"))
    )
    route_window_seconds = window_seconds or int(
        os.getenv(
            f"SICC_ROUTE_{route_key}_RATE_LIMIT_WINDOW_SECONDS",
            os.getenv("SICC_ROUTE_RATE_LIMIT_WINDOW_SECONDS", "60"),
        )
    )

    enforce_rate_limit(
        request=None,
        bucket=f"frontend-route:{route}",
        identifier=user_email.lower(),
        limit=route_limit,
        window_seconds=route_window_seconds,
    )


def enforce_transport_ip_rate_limit(
    request: Request,
    *,
    route: str,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> None:
    route_key = _env_key(route)
    route_limit = limit or int(
        os.getenv(
            f"SICC_TRANSPORT_{route_key}_IP_RATE_LIMIT",
            os.getenv("SICC_TRANSPORT_IP_RATE_LIMIT", "120"),
        )
    )
    route_window_seconds = window_seconds or int(
        os.getenv(
            f"SICC_TRANSPORT_{route_key}_RATE_LIMIT_WINDOW_SECONDS",
            os.getenv("SICC_TRANSPORT_RATE_LIMIT_WINDOW_SECONDS", "60"),
        )
    )

    enforce_rate_limit(
        request,
        bucket=f"transport:{route}:ip",
        identifier=_client_ip(request),
        limit=route_limit,
        window_seconds=route_window_seconds,
    )
