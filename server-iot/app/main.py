from fastapi import FastAPI
from app.routers import devices
from app.routers import commands
from app.routers import agent
from app.database import init_db
import os

app = FastAPI()

app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(agent.router)

@app.get("/")
def root():
    return {"message": "IoT server running"}


@app.on_event("startup")
def on_startup():
    # Only initialize schema if allowed by configuration. The underlying
    # init_db() will check whether the configured DB user has rights.
    init_db()