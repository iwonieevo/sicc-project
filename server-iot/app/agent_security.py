import secrets

from fastapi import HTTPException, Request

from security import load_secure_transport_settings

settings = load_secure_transport_settings(default_identity="iot-server")

INTERNAL_AGENT_TOKEN_HEADER = "x-sicc-internal-agent-token"
AGENT_IDENTITY_HEADER = "x-sicc-agent-identity"
INTERNAL_AGENT_TOKEN = secrets.token_urlsafe(32)
INTERNAL_BACKEND_TOKEN_HEADER = "x-sicc-internal-backend-token"
INTERNAL_BACKEND_TOKEN = secrets.token_urlsafe(32)


def require_backend_transport(request: Request) -> None:
    """Require decrypted backend transport before backend-facing handlers run."""

    if not settings.enabled:
        return

    if request.headers.get(INTERNAL_BACKEND_TOKEN_HEADER) != INTERNAL_BACKEND_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Backend endpoint requires secure transport",
        )


def require_agent_transport(request: Request) -> str | None:
    """Require decrypted agent transport before existing agent handlers run."""

    if not settings.enabled:
        return None

    if request.headers.get(INTERNAL_AGENT_TOKEN_HEADER) != INTERNAL_AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="Agent endpoint requires secure transport")

    identity = request.headers.get(AGENT_IDENTITY_HEADER)
    if not identity:
        raise HTTPException(status_code=403, detail="Agent identity is required")
    return identity
