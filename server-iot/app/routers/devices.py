from fastapi import APIRouter
from app.database import SessionLocal
from app.models import Device

router = APIRouter()


@router.get("/devices")
def get_devices():
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(
            Device.is_deleted == False
        ).order_by(Device.updated_at.desc()).all()
        return [
            {
                "id": d.id,
                "name": d.name,
                "status": d.status,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "registered_at": d.registered_at.isoformat() if d.registered_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None
            }
            for d in devices
        ]
    finally:
        db.close()