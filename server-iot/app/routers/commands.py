from fastapi import APIRouter, HTTPException
from app.database import SessionLocal
from app.models import Command, CommandParameter
from app.schemas import CommandResponse, CommandParameterResponse, CommandCreateRequest


router = APIRouter()


@router.get("/commands", response_model=list[CommandResponse])
def get_commands():
    """Get all available commands with their parameters for backend."""
    db = SessionLocal()
    try:
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
    finally:
        db.close()

@router.post("/commands", response_model=CommandResponse)
def create_command(request: CommandCreateRequest):
    """Create a new command definition."""
    db = SessionLocal()
    try:
        existing = db.query(Command).filter(Command.name == request.name).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Command with this name already exists"
            )

        cmd = Command(
            name=request.name,
            description=request.description,
            python_code=request.python_code
        )

        db.add(cmd)
        db.commit()
        db.refresh(cmd)

        return CommandResponse(
            id=cmd.id,
            name=cmd.name,
            description=cmd.description,
            parameters=[]
        )

    except HTTPException:
        raise
    finally:
        db.close()