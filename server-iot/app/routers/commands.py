from fastapi import APIRouter
from app.database import SessionLocal
from app.models import Command, CommandParameter
from app.utility import build_function


router = APIRouter()


@router.get("/commands")
def get_commands():
    db = SessionLocal()
    try:
        commands = db.query(Command).filter(Command.is_deleted == False).all()
        
        result = []
        for c in commands:
            params = db.query(CommandParameter).filter(
                CommandParameter.command_id == c.id,
                CommandParameter.is_deleted == False
            ).all()

            param_names = [p.name for p in params]
            func_definition = build_function(c.python_code, param_names)

            result.append({
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "func_definition": func_definition,
                "parameters": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "param_type": p.param_type,
                        "is_required": p.is_required,
                        "default_value": p.default_value,
                        "description": p.description
                    }
                    for p in params
                ],
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            })

        return result
    finally:
        db.close()