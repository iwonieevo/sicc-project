import os
import requests
from fastapi import APIRouter, HTTPException
from app.schemas import ResultRequest, SimpleMessageRequest
from app.database import SessionLocal
from app.models import CommandLog, Device

IOT_SERVER_URL = os.getenv("IOT_SERVER_URL", "http://localhost:7000")

router = APIRouter(prefix="/api", tags=["commands"])


def send_to_server(agent_id: str, message: str):
    payload = {
        "device_id": agent_id,
        "command": message
    }

    response = requests.post(f"{IOT_SERVER_URL}/commands", json=payload, timeout=5)
    response.raise_for_status()

    return response.json()


@router.post("/simple-message")
def create_simple_message(data: SimpleMessageRequest):
    try:
        server_response = send_to_server(data.agentId, data.message)
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to forward message: {str(e)}")

    return {
        "status": "forwarded",
        "server_response": server_response.get("command_id")
    }


@router.post("/result")
def receive_result(data: ResultRequest):
    # Results are written by the IoT server directly to the DB; backend accepts notification only.
    # Do not attempt to write to the DB with the backend DB account (read-only for logs).
    # This endpoint exists for notification purposes from IoT server.
    return {"status": "result received"}


@router.get("/results/{command_id}")
def get_result(command_id: int):
    db = SessionLocal()
    try:
        entry = db.query(CommandLog).filter(CommandLog.command_id == command_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Result not found")

        return {
            "command_id": entry.command_id,
            "device_id": entry.device_id,
            "status": entry.status,
            "result": entry.result,
            "created_at": entry.created_at.isoformat() if entry.created_at else None
        }
    finally:
        db.close()


@router.get("/commands")
def list_commands():
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


@router.get("/devices")
def get_devices():
    db = SessionLocal()
    try:
        devices = db.query(Device).all()
        return [
            {"id": d.id, "name": d.name, "host": d.host, "port": d.port, "status": d.status}
            for d in devices
        ]
    finally:
        db.close()