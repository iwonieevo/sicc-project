from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os
from app.database import SessionLocal
from app.models import CommandLog, Device

router = APIRouter()


class CommandRequest(BaseModel):
    device_id: str
    command: str


@router.post("/commands")
def create_command(data: CommandRequest):
    db = SessionLocal()
    try:
        # Create a command log entry in DB
        entry = CommandLog(command_id=None, device_id=int(data.device_id), status="pending", result=None)
        db.add(entry)
        db.commit()
        db.refresh(entry)

        # Mirror id into command_id column for backward compatibility
        entry.command_id = int(entry.id)
        db.commit()

        command_payload = {
            "command_id": entry.command_id,
            "device_id": data.device_id,
            "command": data.command,
            "status": "pending",
            "result": None,
        }

        send_to_agent(command_payload)

        return command_payload
    finally:
        db.close()


@router.get("/commands")
def get_commands():
    db = SessionLocal()
    try:
        entries = db.query(CommandLog).order_by(CommandLog.created_at.desc()).limit(100).all()
        return [
            {
                "command_id": e.command_id,
                "device_id": e.device_id,
                "status": e.status,
                "result": e.result,
                "created_at": e.created_at.isoformat() if e.created_at else None
            }
            for e in entries
        ]
    finally:
        db.close()


def send_to_agent(command):
    AGENT_PORT = int(os.getenv("AGENT_PORT", "9000"))

    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == int(command["device_id"]) ).first()
        if device and device.host:
            agent_host = device.host
            agent_port = device.port or AGENT_PORT
            agent_url = f"http://{agent_host}:{agent_port}/execute"
        else:
            # fallback to conventional name
            agent_url = f"http://agent-{command['device_id']}:{AGENT_PORT}/execute"

        payload = {"command_id": command["command_id"], "command": command["command"]}
        response = requests.post(agent_url, json=payload, timeout=5)
        response.raise_for_status()
    finally:
        db.close()
