from fastapi import APIRouter, HTTPException
import logging

from app.database import SessionLocal
from app.models import Device, Command, CommandQueue, CommandParameter, VCommandLog
from app.schemas import ExecuteRequest, ExecuteResponse, CommandStatusResponse

from app.sanitization import sanitize_parameters

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
        
        param_defs = db.query(CommandParameter).filter(
            CommandParameter.command_id == request.command_id,
            CommandParameter.is_deleted == False
        ).all()

        param_defs_list = [
            {
                "name": p.name,
                "param_type": p.param_type,
                "is_required": p.is_required,
                "default_value": p.default_value
            }
            for p in param_defs
        ]
    
        for param_def in param_defs_list:
            if (
                param_def["is_required"] 
                and param_def["name"] not in request.parameters 
                and param_def["default_value"] is None
            ):
                    
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required parameter: {param_def['name']}"
                )
    
        sanitized_params = sanitize_parameters(request.parameters, param_defs_list)

        queue = CommandQueue(
            device_id=request.device_id,
            command_id=request.command_id,
            parameters=sanitized_params
        )
        db.add(queue)
        db.commit()
        db.refresh(queue)
        
        logger.info(f"Command queued: device={request.device_id}, command={request.command_id}, queue_id={queue.id}")
        return ExecuteResponse(queue_id=queue.id)
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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

@router.get("/logs")
def get_execution_logs(limit: int = 50):
    """Get command execution history."""

    if limit < 0:
        raise HTTPException(
            status_code=400, 
            detail="Limit must be a non-negative integer."
        )
    db = SessionLocal()
    try:
        query = db.query(VCommandLog).order_by(VCommandLog.queued_at.desc())
        
        if limit > 0:
            query = query.limit(limit)
        logs = query.all()

        return [
            {
                "queue_id": log.queue_id,
                "device_id": log.device_id,
                "device_name": log.device_name,
                "command_id": log.command_id,
                "command_name": log.command_name,
                "parameters": log.parameters,
                "status": log.status,
                "result": log.result,
                "is_error": log.is_error,
                "queued_at": log.queued_at.isoformat() if log.queued_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "finished_at": log.finished_at.isoformat() if log.finished_at else None
            }
            for log in logs
        ]
    finally:
        db.close()