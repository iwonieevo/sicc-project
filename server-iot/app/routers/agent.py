from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from app.database import SessionLocal
from app.models import Device, Command, CommandParameter, CommandQueue, CommandExecution, CommandResult
from app.schemas import RegisterRequest, RegisterResponse, CallbackRequest, PollCommandResponse
from app.utility import build_function

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/agent/register", response_model=RegisterResponse)
def register_agent(data: RegisterRequest):
    """Rejestruje nowego agenta w systemie lub przywraca status online dla już istniejącego urządzenia."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.name == data.name).first()
        
        if device:
            if device.is_deleted:
                LOGGER.warning(f"Odrzucono próbę rejestracji usuniętego urządzenia: '{data.name}'")
                raise HTTPException(status_code=400, detail="Device has been deleted")
            
            device.status = "online"
            device.last_seen = datetime.now(timezone.utc)
            db.commit()
            return RegisterResponse(device_id=device.id, status="restored")
        
        device = Device(name=data.name, status="online")
        db.add(device)
        db.commit()
        db.refresh(device)
        
        LOGGER.info(f"Zarejestrowano nowe urządzenie IoT: '{data.name}' (ID: {device.id})")
        return RegisterResponse(device_id=device.id, status="registered")
    finally:
        db.close()


@router.get("/agent/{device_id}/commands", response_model=PollCommandResponse)
def poll_commands(device_id: int):
    """Sprawdza stan urządzenia i pobiera najbliższe oczekujące zadanie z kolejki egzekucyjnej."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(
            Device.id == device_id,
            Device.is_deleted == False
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device.last_seen = datetime.now(timezone.utc)
        
        if device.status == "busy":
            db.commit()
            return PollCommandResponse(queue_id=None, function_code=None, parameters={})

        device.status = "online"
        db.commit()

        queue = db.query(CommandQueue).outerjoin(
            CommandExecution, CommandQueue.id == CommandExecution.queue_id
        ).filter(
            CommandQueue.device_id == device_id,
            CommandExecution.queue_id == None
        ).order_by(CommandQueue.queued_at).first()
        
        if not queue:
            return PollCommandResponse(queue_id=None, function_code=None, parameters={})
        
        command = db.query(Command).filter(
            Command.id == queue.command_id,
            Command.is_deleted == False
        ).first()
        
        if not command:
            return PollCommandResponse(queue_id=None, function_code=None, parameters={})
        
        params = db.query(CommandParameter).filter(
            CommandParameter.command_id == command.id,
            CommandParameter.is_deleted == False
        ).all()
        
        function_code = build_function(command.python_code, [p.name for p in params])
        
        execution = CommandExecution(queue_id=queue.id)
        db.add(execution)
        
        device.status = "busy"
        db.commit()
        
        return PollCommandResponse(
            queue_id=queue.id,
            function_code=function_code,
            parameters=queue.parameters or {}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Błąd podczas odpytywania o zadania dla urządzenia ID {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


@router.post("/agent/callback")
def receive_callback(data: CallbackRequest):
    """Zapisuje raport z wykonania zadania nadesłany przez agenta i przywraca mu status gotowości."""
    db = SessionLocal()
    try:
        queue = db.query(CommandQueue).filter(CommandQueue.id == data.queue_id).first()
        if not queue:
            raise HTTPException(status_code=404, detail="Queue entry not found")
        
        device = db.query(Device).filter(Device.id == queue.device_id).first()
        
        result = CommandResult(
            queue_id=data.queue_id,
            is_error=data.is_error,
            result=data.result
        )
        db.add(result)
        
        if device:
            device.status = "online"
        
        db.commit()
        return {"status": "acknowledged"}
        
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Błąd przetwarzania wyniku zwrotnego (Callback) dla Queue ID {data.queue_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process callback")
    finally:
        db.close()