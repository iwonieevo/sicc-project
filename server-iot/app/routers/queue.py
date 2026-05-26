from fastapi import APIRouter, HTTPException

from app.database import SessionLocal
from app.models import Device, CommandExecution, CommandQueue, VCommandLog
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
        
        log_items = db.query(VCommandLog).filter(
            VCommandLog.device_id == device_id
        ).order_by(
            VCommandLog.queued_at
        ).all()

        return [
            QueueItemResponse(
                queue_id=log.queue_id,
                command_id=log.command_id,
                command_name=log.command_name,
                parameters=log.parameters,
                status=log.status,
                queued_at=str(log.queued_at),
                can_cancel=log.status == "queued"
            )

            for log in log_items
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
        
        command_execution = CommandExecution(queue_id=queue_id, is_cancelled=True)
        db.add(command_execution)
        db.commit()
        db.refresh(command_execution)

        return QueueCancelResponse(
            status="cancelled",
            device_id=device_id,
            queue_id=queue_id
        )
    finally:
        db.close()