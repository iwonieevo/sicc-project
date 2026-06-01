import logging
import os
from datetime import datetime, timezone

from app.agent_security import INTERNAL_AGENT_TOKEN_HEADER, require_agent_transport
from app.agent_security import settings as secure_settings
from app.database import get_db
from app.enrollment import verify_enrollment_token
from app.models import (
    Command,
    CommandExecution,
    CommandParameter,
    CommandQueue,
    CommandResult,
    Device,
)
from app.schemas import (
    CallbackRequest,
    PollCommandResponse,
    RegisterRequest,
    RegisterResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from security import public_key_id
from security.encoding import b64decode

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def validate_device_public_key(
    public_key_id_value: str | None, public_key_value: str | None
) -> tuple[str | None, str | None]:
    if public_key_id_value is None and public_key_value is None:
        return None, None
    if public_key_id_value is None or public_key_value is None:
        raise HTTPException(
            status_code=400, detail="Both public_key_id and public_key are required"
        )

    try:
        raw_public_key = b64decode(public_key_value)
    except Exception:
        raise HTTPException(status_code=400, detail="public_key must be base64 encoded")

    if len(raw_public_key) != 32:
        raise HTTPException(
            status_code=400, detail="public_key must decode to 32 bytes"
        )
    if public_key_id(raw_public_key) != public_key_id_value:
        raise HTTPException(
            status_code=400, detail="public_key_id does not match public_key"
        )

    return public_key_id_value, public_key_value


@router.post("/agent/register", response_model=RegisterResponse)
def register_agent(
    data: RegisterRequest, request: Request, db: Session = Depends(get_db)
):
    """Registers a new agent or restores online status for an existing one. Returns device_id and registration status."""

    secure_identity = None
    if request.headers.get(INTERNAL_AGENT_TOKEN_HEADER) is not None:
        secure_identity = require_agent_transport(request)
    if secure_identity is not None and secure_identity != data.name:
        raise HTTPException(status_code=403, detail="Agent identity mismatch")

    public_key_id_value, public_key_value = validate_device_public_key(
        data.public_key_id, data.public_key
    )
    device = db.query(Device).filter(Device.name == data.name).first()

    if secure_settings.enabled:
        if public_key_id_value is None or public_key_value is None:
            LOGGER.warning(
                "Secure registration rejected without submitted public key: '%s'",
                data.name,
            )
            raise HTTPException(status_code=403, detail="Device public key is required")

        if device is None or (
            device.public_key_id is None and device.public_key is None
        ):
            enrollment_secret = os.getenv("SICC_AGENT_ENROLLMENT_SECRET")
            if enrollment_secret is None:
                LOGGER.warning("Secure registration rejected without enrollment secret")
                raise HTTPException(
                    status_code=500, detail="Agent enrollment is not configured"
                )
            if data.enrollment_token is None or not verify_enrollment_token(
                enrollment_secret, data.enrollment_token, data.name
            ):
                LOGGER.warning(
                    "Secure registration rejected for invalid enrollment token: '%s'",
                    data.name,
                )
                raise HTTPException(
                    status_code=403, detail="Device enrollment token is invalid"
                )
        elif (
            device.public_key_id != public_key_id_value
            or device.public_key != public_key_value
        ):
            LOGGER.warning(
                "Secure registration rejected for device key mismatch: '%s'",
                device.name,
            )
            raise HTTPException(status_code=403, detail="Device public key mismatch")

    if device:
        if device.is_deleted:
            LOGGER.warning(
                f"Registration attempt rejected for deleted device: '{data.name}'"
            )
            raise HTTPException(status_code=400, detail="Device has been deleted")

        if public_key_id_value is not None:
            if device.public_key_id is None and device.public_key is None:
                device.public_key_id = public_key_id_value
                device.public_key = public_key_value
            elif (
                device.public_key_id != public_key_id_value
                or device.public_key != public_key_value
            ):
                LOGGER.warning(
                    f"Registration attempt rejected for device key mismatch: '{data.name}'"
                )
                raise HTTPException(
                    status_code=400, detail="Device public key mismatch"
                )

        device.status = "online"
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        LOGGER.info(f"Device restored to online: '{data.name}' (ID: {device.id})")
        return RegisterResponse(device_id=device.id, status="restored")

    device = Device(
        name=data.name,
        public_key_id=public_key_id_value,
        public_key=public_key_value,
        status="online",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    LOGGER.info(f"New device registered: '{data.name}' (ID: {device.id})")
    return RegisterResponse(device_id=device.id, status="registered")


@router.get("/agent/{device_id}/commands", response_model=PollCommandResponse)
def poll_commands(device_id: int, request: Request, db: Session = Depends(get_db)):
    """Checks device status and returns the next pending task from the execution queue, if available."""
    try:
        secure_identity = require_agent_transport(request)
        device = (
            db.query(Device)
            .filter(Device.id == device_id, Device.is_deleted == False)
            .first()
        )

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        if secure_identity is not None and device.name != secure_identity:
            raise HTTPException(status_code=403, detail="Agent identity mismatch")

        device.last_seen = datetime.now(timezone.utc)
        device.status = "online"

        queue, execution_id = (
            db.query(CommandQueue, CommandExecution.queue_id)
            .outerjoin(CommandExecution, CommandQueue.id == CommandExecution.queue_id)
            .outerjoin(CommandResult, CommandQueue.id == CommandResult.queue_id)
            .filter(
                CommandQueue.device_id == device_id,
                func.coalesce(CommandExecution.is_cancelled, False) == False,
                CommandResult.queue_id == None,
            )
            .order_by(CommandQueue.queued_at)
            .first()
        ) or (None, None)

        if not queue:
            db.commit()
            return PollCommandResponse(
                queue_id=None, function_code=None, parameters=None
            )

        command = (
            db.query(Command)
            .filter(Command.id == queue.command_id, Command.is_deleted == False)
            .first()
        )

        if not command:
            LOGGER.warning(
                f"Queue entry {queue.id} references a missing or deleted command (ID: {queue.command_id}), skipping."
            )
            db.commit()
            return PollCommandResponse(
                queue_id=None, function_code=None, parameters=None
            )

        params = (
            db.query(CommandParameter)
            .filter(
                CommandParameter.command_id == command.id,
                CommandParameter.is_deleted == False,
            )
            .all()
        )

        params = ", ".join([p.name for p in params])
        function_def = f"def _sicc_command({params}):\n"
        indented_code = "\n".join(
            f"\t{line}" for line in command.python_code.splitlines()
        )
        function_code = function_def + indented_code + "\n"

        if not execution_id:
            execution = CommandExecution(queue_id=queue.id)
            db.add(execution)

        device.status = "busy"
        db.commit()

        LOGGER.debug(
            f"Task dispatched to device ID {device_id} (Queue ID: {queue.id}, Command ID: {command.id})"
        )
        return PollCommandResponse(
            queue_id=queue.id,
            function_code=function_code,
            parameters=queue.parameters or {},
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error polling commands for device ID {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/agent/callback")
def receive_callback(
    data: CallbackRequest, request: Request, db: Session = Depends(get_db)
):
    """Records the execution result reported by an agent and restores its online status."""
    try:
        secure_identity = require_agent_transport(request)
        queue = db.query(CommandQueue).filter(CommandQueue.id == data.queue_id).first()
        if not queue:
            raise HTTPException(status_code=404, detail="Queue entry not found")

        device = db.query(Device).filter(Device.id == queue.device_id).first()
        if not device:
            LOGGER.warning(
                f"Device not found when processing callback for Queue ID {data.queue_id} (Device ID: {queue.device_id})"
            )
        else:
            if secure_identity is not None and device.name != secure_identity:
                raise HTTPException(status_code=403, detail="Agent identity mismatch")
            device.status = "online"

        result = CommandResult(
            queue_id=data.queue_id, is_error=data.is_error, result=data.result
        )
        db.add(result)

        db.commit()

        if data.is_error:
            LOGGER.warning(
                f"Task reported failure (Queue ID: {data.queue_id}): {data.result}"
            )
        else:
            LOGGER.info(f"Task result acknowledged (Queue ID: {data.queue_id})")

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error processing callback for Queue ID {data.queue_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process callback")
