import os
import requests
import os
from fastapi import APIRouter, HTTPException
from app.schemas import ResultRequest, SimpleMessageRequest

IOT_SERVER_URL = os.getenv("IOT_SERVER_URL", "http://localhost:7000")

router = APIRouter(prefix="/api", tags=["commands"])

results_store = {}

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
        "server_response": server_response["command_id"]
    }

@router.post("/result")
def receive_result(data: ResultRequest):
    results_store[data.command_id] = {
        "command_id": data.command_id,
        "device_id": data.device_id,
        "status": data.status,
        "result": data.result
    }

    return {"status": "result received"}

@router.get("/results/{command_id}")
def get_result(command_id: int):
    result = results_store.get(command_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")

    return result