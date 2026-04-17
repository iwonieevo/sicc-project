from fastapi import FastAPI
from pydantic import BaseModel
import requests
import os

app = FastAPI()

SERVER = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")
DEVICE = os.getenv("AGENT_ID", -1)

class ExecuteRequest(BaseModel):
    command_id: int
    command: str

@app.post("/execute")
def execute_command(data: ExecuteRequest):
    try:
        exec(data.command)
        result = "OK"
    except Exception as e:
        result = str(e)

    requests.post(
        f"{SERVER}/agent/commands/{data.command_id}/done",
        json={"result": result}
    )

    return {"status": "executed"}