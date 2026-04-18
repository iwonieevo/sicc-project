from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, commands
from app.database import init_db, SessionLocal
from app.models import User
from app.auth import hash_password
import logging
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(commands.router)


@app.on_event("startup")
def on_startup():
    # Ensure DB tables exist when allowed by configuration
    init_db()

    # Seed three default users if they don't exist: admin, iot-server, backend
    # Any permission errors during seeding should not crash the app startup.
    db = SessionLocal()
    try:
        for email, pwd in [
            ("admin@example.com", "admin"),
            ("iot-server@example.com", "iot-server"),
            ("backend@example.com", "backend"),
        ]:
            try:
                existing = db.query(User).filter(User.email == email).first()
                if not existing:
                    u = User(email=email, hashed_password=hash_password(pwd))
                    db.add(u)
            except Exception:
                logging.exception("Failed to check/create seeded user %s", email)
        try:
            db.commit()
        except Exception:
            logging.exception("Failed to commit seeded users")
    finally:
        db.close()