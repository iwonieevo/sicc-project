from app.agent_security import require_backend_transport
from app.database import get_db
from app.models import Command, CommandParameter
from app.schemas import CommandCreateRequest, CommandParameterResponse, CommandResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(dependencies=[Depends(require_backend_transport)])


@router.get("/commands", response_model=list[CommandResponse])
def get_commands(db: Session = Depends(get_db)):
    """Get all available commands with their parameters for backend."""
    commands = db.query(Command).filter(Command.is_deleted == False).all()
    result = []

    for cmd in commands:
        params = (
            db.query(CommandParameter)
            .filter(CommandParameter.command_id == cmd.id, CommandParameter.is_deleted == False)
            .all()
        )

        param_responses = [
            CommandParameterResponse(
                id=p.id,
                name=p.name,
                param_type=p.param_type,
                is_required=p.is_required,
                default_value=p.default_value,
                description=p.description,
            )
            for p in params
        ]

        result.append(
            CommandResponse(
                id=cmd.id,
                name=cmd.name,
                description=cmd.description,
                parameters=param_responses,
            )
        )

    return result


@router.post("/commands", response_model=CommandResponse)
def create_command(request: CommandCreateRequest, db: Session = Depends(get_db)):
    """Create a new command definition."""
    try:
        existing = db.query(Command).filter(Command.name == request.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Command with this name already exists")

        cmd = Command(name=request.name, description=request.description, python_code=request.python_code)

        db.add(cmd)
        db.commit()
        db.refresh(cmd)

        return CommandResponse(id=cmd.id, name=cmd.name, description=cmd.description, parameters=[])

    except HTTPException:
        raise
