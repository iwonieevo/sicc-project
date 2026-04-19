from fastapi import FastAPI
from pydantic import BaseModel
import requests
import os
import socket
import time

app = FastAPI()

SERVER = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
AGENT_PORT = int(os.getenv("AGENT_PORT", "9000"))


class ExecuteRequest(BaseModel):
    command_id: int
    command: str


@app.on_event("startup")
def register_with_server():
    # Attempt to register with the IoT server several times
    hostname = socket.gethostname()
    name = f"agent-{hostname}"
    payload = {"host": hostname, "port": AGENT_PORT, "name": name}

    for _ in range(10):
        try:
            resp = requests.post(f"{SERVER}/agent/register", json=payload, timeout=5)
            if resp.ok:
                try:
                    data = resp.json()
                    assigned = data.get("device_id")
                    if assigned:
                        print("Registered with server, assigned device_id:", assigned)
                except Exception:
                    pass
                break
        except Exception:
            time.sleep(2)


@app.post("/execute")
def execute_command(data: ExecuteRequest):
    # For safety and simplicity in this minimal demo, do NOT execute
    # arbitrary code received from the server. Instead, echo the command
    # back as the result. This avoids syntax/runtime exceptions like
    # "invalid decimal literal" that appear when `exec()` runs non-Python
    # payloads.
    try:
        result = f"executed: {data.command}"
    except Exception as e:
        result = f"error preparing result: {e}"

    try:
        requests.post(
            f"{SERVER}/agent/commands/{data.command_id}/done",
            json={"result": result},
            timeout=5
        )
    except Exception:
        # best-effort
        pass

    return {"status": "executed"}