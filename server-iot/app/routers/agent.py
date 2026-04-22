from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from app.database import SessionLocal
from app.models import Device, Command, CommandParameter, CommandQueue, CommandExecution, CommandResult
from app.schemas import RegisterRequest, RegisterResponse, CallbackRequest, PollCommandResponse
from app.utility import build_function


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/agent/register", response_model=RegisterResponse)
def register_agent(data: RegisterRequest):
    """Register new agent or restore existing one. Sets status to online."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.name == data.name).first()
        
        if device:
            if device.is_deleted:
                logger.warning(f"Deleted device '{data.name}' attempted re-registration")
                raise HTTPException(status_code=400, detail="Device has been deleted")
            
            device.status = "online"
            device.last_seen = datetime.now(timezone.utc)
            db.commit()
            return RegisterResponse(device_id=device.id, status="restored")
        
        device = Device(name=data.name, status="online")
        db.add(device)
        db.commit()
        db.refresh(device)
        
        logger.info(f"New device registered: id={device.id}, name={device.name}")
        return RegisterResponse(device_id=device.id, status="registered")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")
    finally:
        db.close()


@router.get("/agent/{device_id}/commands")
def poll_commands(device_id: int):
    """
    Return next pending command for device, or empty response if none available.
    Does not return 404 - empty response indicates no commands.
    """
    db = SessionLocal()
    try:
        device = db.query(Device).filter(
            Device.id == device_id,
            Device.is_deleted == False
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device.last_seen = datetime.now(timezone.utc)
        device.status = "online"
        db.commit()
        
        queue = db.query(CommandQueue).outerjoin(
            CommandExecution, CommandQueue.id == CommandExecution.queue_id
        ).filter(
            CommandQueue.device_id == device_id,
            CommandExecution.queue_id == None
        ).order_by(CommandQueue.queued_at).first()
        
        if not queue:
            return {}
        
        command = db.query(Command).filter(
            Command.id == queue.command_id,
            Command.is_deleted == False
        ).first()
        
        if not command:
            logger.warning(f"Command {queue.command_id} not found for queue {queue.id}")
            return {}
        
        params = db.query(CommandParameter).filter(
            CommandParameter.command_id == command.id,
            CommandParameter.is_deleted == False
        ).all()
        
        function_code = build_function(command.python_code, [p.name for p in params])
        
        execution = CommandExecution(queue_id=queue.id)
        db.add(execution)
        device.status = "busy"
        db.commit()
        
        return {
            "queue_id": queue.id,
            "function_code": function_code,
            "parameters": queue.parameters or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Poll error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve commands")
    finally:
        db.close()


@router.post("/agent/callback")
def receive_callback(data: CallbackRequest):
    """Receive and store command execution result."""
    db = SessionLocal()
    try:
        queue = db.query(CommandQueue).filter(CommandQueue.id == data.queue_id).first()
        if not queue:
            raise HTTPException(status_code=404, detail="Queue entry not found")
        
        device = db.query(Device).filter(
            Device.id == queue.device_id,
            Device.is_deleted == False
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        result = CommandResult(
            queue_id=data.queue_id,
            is_error=data.is_error,
            result=data.result
        )
        db.add(result)
        
        device.last_seen = datetime.now(timezone.utc)
        device.status = "online"
        db.commit()
        
        return {"status": "acknowledged"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Callback error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process callback")
    finally:
        db.close()