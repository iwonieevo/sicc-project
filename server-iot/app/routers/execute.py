from fastapi import APIRouter, HTTPException
import logging

from app.database import SessionLocal
from app.models import Device, Command, CommandQueue, VCommandLog
from app.schemas import ExecuteRequest, ExecuteResponse, CommandStatusResponse


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_command(request: ExecuteRequest):
    """Queue command for execution by specified device."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(
            Device.id == request.device_id,
            Device.is_deleted == False
        ).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        command = db.query(Command).filter(
            Command.id == request.command_id,
            Command.is_deleted == False
        ).first()
        if not command:
            raise HTTPException(status_code=404, detail="Command not found")
        
        queue = CommandQueue(
            device_id=request.device_id,
            command_id=request.command_id,
            parameters=request.parameters
        )
        db.add(queue)
        db.commit()
        db.refresh(queue)
        
        logger.info(f"Command queued: device={request.device_id}, command={request.command_id}, queue_id={queue.id}")
        return ExecuteResponse(queue_id=queue.id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute error: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue command")
    finally:
        db.close()


@router.get("/status/{queue_id}", response_model=CommandStatusResponse)
def get_command_status(queue_id: int):
    """Get current status and result of queued command."""
    db = SessionLocal()
    try:
        log = db.query(VCommandLog).filter(VCommandLog.queue_id == queue_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")
        
        return CommandStatusResponse(
            queue_id=log.queue_id,
            device_id=log.device_id,
            command_id=log.command_id,
            parameters=log.parameters,
            queued_at=log.queued_at.isoformat() if log.queued_at else None,
            started_at=log.started_at.isoformat() if log.started_at else None,
            finished_at=log.finished_at.isoformat() if log.finished_at else None,
            is_error=log.is_error,
            result=log.result,
            status=log.status
        )
    finally:
        db.close()