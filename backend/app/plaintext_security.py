import secrets

from app.secure_transport import settings
from fastapi import HTTPException, Request

INTERNAL_FRONTEND_TOKEN_HEADER = "x-sicc-internal-frontend-token"
INTERNAL_FRONTEND_TOKEN = secrets.token_urlsafe(32)


def require_frontend_secure_transport(request: Request) -> None:
    """Reject direct plaintext frontend API calls when secure mode is enabled."""

    if not settings.enabled:
        return

    if request.headers.get(INTERNAL_FRONTEND_TOKEN_HEADER) != INTERNAL_FRONTEND_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Frontend endpoint requires secure transport",
        )
