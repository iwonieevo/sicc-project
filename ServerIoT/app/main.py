from fastapi import FastAPI
from app.routers import devices
from app.routers import commands
from app.routers import agent

app = FastAPI()

app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(agent.router)

@app.get("/")
def root():
    return {"message": "IoT server running"}