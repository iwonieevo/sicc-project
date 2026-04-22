from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from app.routers import auth, commands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

app = FastAPI(title="Secure IoT Control Center API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(commands.router)


@app.get("/")
def root():
    return {"message": "Secure IoT Control Center API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}