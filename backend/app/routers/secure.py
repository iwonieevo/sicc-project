import logging

import httpx
from app.auth import get_current_user
from app.secure_transport import initiate_backend_iot_handshake
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from security import CryptoError

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/secure", tags=["secure-transport"])


class BackendIotHandshakeResponse(BaseModel):
    session_id: str
    status: str


@router.post("/backend-iot/handshake", response_model=BackendIotHandshakeResponse)
def create_backend_iot_handshake(_current_user: dict = Depends(get_current_user)):
    """Diagnostic endpoint that manually triggers the backend-IoT handshake."""

    try:
        session = initiate_backend_iot_handshake()
    except httpx.HTTPStatusError as exc:
        LOGGER.warning(
            "IoT server rejected backend-IoT secure handshake: %s",
            exc.response.status_code,
        )
        raise HTTPException(status_code=502, detail="secure handshake failed") from exc
    except httpx.HTTPError as exc:
        LOGGER.warning("IoT server unavailable during secure handshake: %s", exc)
        raise HTTPException(status_code=503, detail="IoT server unavailable") from exc
    except (CryptoError, ValueError, AssertionError) as exc:
        LOGGER.warning("Backend-IoT secure handshake failed: %s", exc)
        raise HTTPException(status_code=400, detail="secure handshake failed") from exc

    return BackendIotHandshakeResponse(
        session_id=session.transcript.session_id,
        status="established",
    )
