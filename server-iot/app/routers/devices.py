from fastapi import APIRouter
from app.database import SessionLocal
from app.models import Device
from app.schemas import DeviceResponse


router = APIRouter()


@router.get("/devices", response_model=list[DeviceResponse])
def get_devices():
    """Get all registered devices for backend."""
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(
            Device.is_deleted == False
        ).all()

        return [
            DeviceResponse(
                id=d.id,
                name=d.name,
                status=d.status,
                last_seen=d.last_seen,
            )
            for d in devices
        ]
    finally:
        db.close()