from fastapi import APIRouter
import os

router = APIRouter()

num_agents = int(os.getenv("NUM_AGENTS", 2))
devices = [
    {"device_id": i, "name": f"Agent-{i}", "status": "offline", "last_seen": None}
    for i in range(1, num_agents + 1)
]

@router.get("/devices")
def get_devices():
    return devices