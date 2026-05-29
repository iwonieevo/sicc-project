import logging
from datetime import datetime, timezone

from app.database import get_db
from app.models import (
    Command,
    CommandExecution,
    CommandParameter,
    CommandQueue,
    CommandResult,
    Device,
)
from app.schemas import CallbackRequest, PollCommandResponse, RegisterRequest, RegisterResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/agent/register", response_model=RegisterResponse)
def register_agent(data: RegisterRequest, db: Session = Depends(get_db)):
    """Registers a new agent or restores online status for an existing one. Returns device_id and registration status."""
    device = db.query(Device).filter(Device.name == data.name).first()

    if device:
        if device.is_deleted:
            LOGGER.warning(f"Registration attempt rejected for deleted device: '{data.name}'")
            raise HTTPException(status_code=400, detail="Device has been deleted")

        device.status = "online"
        device.last_seen = datetime.now(timezone.utc)
        db.commit()
        LOGGER.info(f"Device restored to online: '{data.name}' (ID: {device.id})")
        return RegisterResponse(device_id=device.id, status="restored")

    device = Device(name=data.name, status="online")
    db.add(device)
    db.commit()
    db.refresh(device)

    LOGGER.info(f"New device registered: '{data.name}' (ID: {device.id})")
    return RegisterResponse(device_id=device.id, status="registered")


@router.get("/agent/{device_id}/commands", response_model=PollCommandResponse)
def poll_commands(device_id: int, db: Session = Depends(get_db)):
    """Checks device status and returns the next pending task from the execution queue, if available."""
    try:
        device = db.query(Device).filter(Device.id == device_id, Device.is_deleted == False).first()

        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

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
            return PollCommandResponse(queue_id=None, function_code=None, parameters=None)

        command = (
            db.query(Command).filter(Command.id == queue.command_id, Command.is_deleted == False).first()
        )

        if not command:
            LOGGER.warning(
                f"Queue entry {queue.id} references a missing or deleted command (ID: {queue.command_id}), skipping."
            )
            db.commit()
            return PollCommandResponse(queue_id=None, function_code=None, parameters=None)

        params = (
            db.query(CommandParameter)
            .filter(CommandParameter.command_id == command.id, CommandParameter.is_deleted == False)
            .all()
        )

        params = ", ".join([p.name for p in params])
        function_def = f"def _sicc_command({params}):\n"
        indented_code = "\n".join(f"\t{line}" for line in command.python_code.splitlines())
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
            queue_id=queue.id, function_code=function_code, parameters=queue.parameters or {}
        )

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error polling commands for device ID {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/agent/callback")
def receive_callback(data: CallbackRequest, db: Session = Depends(get_db)):
    """Records the execution result reported by an agent and restores its online status."""
    try:
        queue = db.query(CommandQueue).filter(CommandQueue.id == data.queue_id).first()
        if not queue:
            raise HTTPException(status_code=404, detail="Queue entry not found")

        device = db.query(Device).filter(Device.id == queue.device_id).first()
        if not device:
            LOGGER.warning(
                f"Device not found when processing callback for Queue ID {data.queue_id} (Device ID: {queue.device_id})"
            )
        else:
            device.status = "online"

        result = CommandResult(queue_id=data.queue_id, is_error=data.is_error, result=data.result)
        db.add(result)

        db.commit()

        if data.is_error:
            LOGGER.warning(f"Task reported failure (Queue ID: {data.queue_id}): {data.result}")
        else:
            LOGGER.info(f"Task result acknowledged (Queue ID: {data.queue_id})")

    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error processing callback for Queue ID {data.queue_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process callback")
