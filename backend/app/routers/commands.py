import os
import requests
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Command, CommandParameter, Device, VCommandLog
from app.schemas import (
    CommandResponse, CommandParameterResponse, DeviceResponse, CommandStatusResponse,
    ExecuteCommandRequest, ExecuteCommandResponse, CommandCreateRequest, ResultCallbackRequest
)
from app.sanitization import sanitize_parameters
from app.auth import get_current_user

IOT_SERVER_URL = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["commands"])


def get_db():
    """Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/devices", response_model=list[DeviceResponse])
def list_devices(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all registered devices."""
    devices = db.query(Device).filter(Device.is_deleted == False).all()
    return [
        DeviceResponse(
            id=d.id,
            name=d.name,
            status=d.status,
            last_seen=d.last_seen
        )
        for d in devices
    ]


@router.get("/commands", response_model=list[CommandResponse])
def list_commands(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all available commands with their parameters."""
    commands = db.query(Command).filter(Command.is_deleted == False).all()
    result = []
    
    for cmd in commands:
        params = db.query(CommandParameter).filter(
            CommandParameter.command_id == cmd.id,
            CommandParameter.is_deleted == False
        ).all()
        
        param_responses = [
            CommandParameterResponse(
                id=p.id,
                name=p.name,
                param_type=p.param_type,
                is_required=p.is_required,
                default_value=p.default_value,
                description=p.description
            )
            for p in params
        ]
        
        result.append(CommandResponse(
            id=cmd.id,
            name=cmd.name,
            description=cmd.description,
            parameters=param_responses
        ))
    
    return result


@router.post("/execute", response_model=ExecuteCommandResponse)
def execute_command(
    request: ExecuteCommandRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Queue a command for execution on a device."""
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
        if param_def["is_required"] and param_def["name"] not in request.parameters and not param_def["default_value"]:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required parameter: {param_def['name']}"
            )
    
    sanitized_params = sanitize_parameters(request.parameters, param_defs_list)
    
    try:
        response = requests.post(
            f"{IOT_SERVER_URL}/execute",
            json={
                "device_id": request.device_id,
                "command_id": request.command_id,
                "parameters": sanitized_params
            },
            timeout=5
        )
        response.raise_for_status()
        response_data = response.json()
        
        logger.info(f"Command queued: queue_id={response_data['queue_id']}, user={current_user['email']}")
        
        return ExecuteCommandResponse(
            queue_id=response_data["queue_id"],
            status_url=f"/api/status/{response_data['queue_id']}"
        )
        
    except requests.RequestException as e:
        logger.error(f"Failed to forward command to IoT server: {e}")
        raise HTTPException(status_code=503, detail="IoT server unavailable")
    

@router.get("/logs")
def get_execution_logs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 50
):
    """Get command execution history."""
    logs = db.query(VCommandLog).order_by(VCommandLog.queued_at.desc()).limit(limit).all()

    return [
        {
            "queue_id": log.queue_id,
            "device_id": log.device_id,
            "command_id": log.command_id,
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


@router.get("/status/{queue_id}", response_model=CommandStatusResponse)
def get_command_status(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current status and result of a queued command."""
    log = db.query(VCommandLog).filter(VCommandLog.queue_id == queue_id).first()
    
    if not log:
        raise HTTPException(status_code=404, detail="Command not found")
    
    return CommandStatusResponse(
        queue_id=log.queue_id,
        device_id=log.device_id,
        command_id=log.command_id,
        parameters=log.parameters,
        status=log.status,
        result=log.result,
        is_error=log.is_error,
        queued_at=log.queued_at,
        started_at=log.started_at,
        finished_at=log.finished_at
    )


@router.post("/commands", response_model=CommandResponse)
def create_command(
    request: CommandCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new command definition."""
    existing = db.query(Command).filter(Command.name == request.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Command with this name already exists")
    
    cmd = Command(
        name=request.name,
        description=request.description,
        python_code=request.python_code
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    
    logger.info(f"Command created: {cmd.name} by {current_user['email']}")
    
    return CommandResponse(
        id=cmd.id,
        name=cmd.name,
        description=cmd.description,
        parameters=[]
    )


@router.post("/result")
def receive_result(request: ResultCallbackRequest):
    """
    Receive result notification from IoT server.
    This endpoint is public - called by IoT server.
    """
    logger.info(f"Result received: queue_id={request.queue_id}, is_error={request.is_error}")
    return {"status": "acknowledged"}