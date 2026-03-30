from fastapi import FastAPI
from pydantic import BaseModel
from fastapi import HTTPException

devices = [
    {"device_id" : 0, "name" : "RasberryPi", "status" : "online"},
    {"device_id" : 1, "name" : "RasberryPi", "status" : "offline"},
    {"device_id" : 2, "name" : "RasberryPi", "status" : "offline"}
]

commands = []

class CommandRequest(BaseModel):
    device_id: int
    command: str
    
app = FastAPI()



# Komunikacja z aplikacją

 

@app.get("/")
def root():
    return {"message" : "IoT server running"}

# Endpoint zwracający listę wszystkich dostępnych urządzeń wraz z ich identyfikatorami i aktualnym stanem (online/offline).
@app.get("/devices")
def get_devices():
    return devices

# Endpoint umożliwiający utworzenie nowej komendy dla wskazanego urządzenia.
# Serwer weryfikuje istnienie urządzenia oraz jego stan (online),
# a następnie zapisuje komendę w pamięci ze statusem "pending".
@app.post("/commands")
def create_command(data: CommandRequest):
    
    found = False
    new_device = None

    for device in devices:
        if device["device_id"] == data.device_id:
            found = True
            new_device = device
            break
        
    if not found:
        raise HTTPException(status_code=404, detail="Device not found")
    if new_device["status"] == "offline":
        raise HTTPException(status_code=400, detail="Device is offline")

    new_command = {
        "command_id" : len(commands),
        "device_id" : data.device_id,
        "command" : data.command,
        "status" : "pending" 
        }

    commands.append(new_command)

    return new_command

# Endpoint zwracający listę wszystkich komend zapisanych na serwerze
# wraz z ich aktualnym statusem wykonania.
@app.get("/commands")
def get_commands():
    return commands



# Komunikacja z agentem


        
# Endpoint dla agenta, który pozwoli mu pobrać czekające na niego zadania
@app.get("/agent/{device_id}/commands")
def get_waiting_commands(device_id: int):

    found = False
    new_device = None

    for device in devices:
        if device["device_id"] == device_id:
            found = True
            new_device = device
            break        
    
    if not found:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if new_device["status"] == "offline":
        raise HTTPException(status_code=400, detail="Device is offline")
    
    pending_commands = []

    for command in commands:
        if command["device_id"] == device_id and command["status"] == "pending":
            pending_commands.append(command)

    return pending_commands
    
    
# Endpoint dla agenta, który pozwoli mu zwrócić zrobione zadania
@app.post("/agent/commands/{command_id}/done")
def mark_command_done(command_id: int):
    for command in commands:
        if command["command_id"] == command_id:
            command["status"] = "done"
            return command
    
    raise HTTPException(status_code=404, detail="Command not found")

