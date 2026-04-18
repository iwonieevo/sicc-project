from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os

from app.database import SessionLocal
from app.models import Device, CommandLog

router = APIRouter()
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


# Model danych odbieranych od agenta
class CommandResult(BaseModel):
    result: str


class RegisterRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    name: str | None = None


@router.post("/agent/register")
def register_agent(data: RegisterRequest):
    db = SessionLocal()
    try:
        # Try find existing device by host/port or name
        device = None
        if data.host and data.port:
            device = db.query(Device).filter(Device.host == data.host, Device.port == data.port).first()
        if not device and data.name:
            device = db.query(Device).filter(Device.name == data.name).first()

        if device:
            device.host = data.host or device.host
            device.port = data.port or device.port
            device.name = data.name or device.name
            device.status = "online"
        else:
            device = Device(name=data.name, host=data.host, port=data.port, status="online")
            db.add(device)
            db.commit()
            db.refresh(device)

        db.commit()
        return {"status": "registered", "device_id": device.id}
    finally:
        db.close()


# Endpoint odbierający wynik wykonania komendy od agenta
@router.post("/agent/commands/{command_id}/done")
def mark_done(command_id: int, data: CommandResult):
    db = SessionLocal()
    try:
        entry = db.query(CommandLog).filter(CommandLog.command_id == command_id).first()
        if entry:
            entry.status = "done"
            entry.result = data.result
            db.commit()
        else:
            # Insert if not present
            entry = CommandLog(command_id=command_id, device_id=None, status="done", result=data.result)
            db.add(entry)
            db.commit()

        send_result_to_web_server({
            "command_id": command_id,
            "device_id": entry.device_id,
            "status": "done",
            "result": data.result
        })

        return {"status": "updated"}
    finally:
        db.close()


def send_result_to_web_server(command):
    backend_api_url = BACKEND_URL + "/api/result"

    payload = {
        "command_id": command.get("command_id"),
        "device_id": command.get("device_id"),
        "status": command.get("status"),
        "result": command.get("result")
    }

    try:
        requests.post(backend_api_url, json=payload, timeout=5)
    except Exception as e:
        print("Failed sending result to backend:", e)
