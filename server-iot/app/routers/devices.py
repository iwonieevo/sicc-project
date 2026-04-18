from fastapi import APIRouter
from app.database import SessionLocal
from app.models import Device

router = APIRouter()


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