from fastapi import APIRouter, HTTPException

from app.database import SessionLocal
from app.models import Device, Command, CommandQueue, VCommandLog
from app.schemas import QueueItemResponse, QueueCancelResponse


router = APIRouter()

@router.get("/devices/{device_id}/queue", response_model=list[QueueItemResponse])
def get_device_queue(device_id: int):
    """Get command queue for selected device"""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(
            Device.id == device_id,
            Device.is_deleted == False
        ).first()

        if not device:
            raise HTTPException(
                status_code=404,
                detail="Device not found"
            )
        
        queue_items = db.query(VCommandLog, Command).join(
            Command,
            VCommandLog.command_id == Command.id
        ).filter(
            VCommandLog.device_id == device_id
        ).order_by(
            VCommandLog.queued_at
        ).all()

        return [
            QueueItemResponse(
                queue_id=log.queue_id,
                command_id=log.command_id,
                command_name=command.name,
                parameters=log.parameters,
                status=log.status,
                can_cancel=log.status == "queued"
            )

            for log, command in queue_items
        ]
    
    finally:
        db.close()

@router.post("/devices/{device_id}/queue/{queue_id}/cancel", response_model=QueueCancelResponse)
def cancel_queue_task(device_id: int, queue_id: int):
    """Cancel queued command if it has not been started yet"""

    db = SessionLocal()
    try:
        queue_log = db.query(VCommandLog).filter(
            VCommandLog.queue_id == queue_id,
            VCommandLog.device_id == device_id
        ).first()

        if not queue_log:
            raise HTTPException(
                status_code=404,
                detail="Queue task not found"
            )
        
        if queue_log.status != "queued":
            raise HTTPException(
                status_code=409,
                detail="Cannot cancel task that is already running or finished"
            )
        
        queue_task = db.query(CommandQueue).filter(
            CommandQueue.id == queue_id,
            CommandQueue.device_id == device_id
        ).first()

        if not queue_task:
            raise HTTPException(
                status_code=404,
                detail="Queue task not found"
            )
        
        queue_task.is_cancelled = True
        db.commit()

        return QueueCancelResponse(
            status="cancelled",
            device_id=device_id,
            queue_id=queue_id
        )
    finally:
        db.close()