from fastapi import FastAPI
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.routers import devices, commands, agent, execute, queue
from app.database import SessionLocal
from app.models import Device

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)


async def monitor_device_status():
    """
    Background task that checks device statuses every 30 seconds.
    
    Devices that are not 'busy' and haven't been seen for over 30 seconds
    are marked as 'offline'.
    """
    while True:
        try:
            await asyncio.sleep(30)
            
            db = SessionLocal()
            try:
                threshold = datetime.now(timezone.utc) - timedelta(seconds=20)
                
                devices_to_update = db.query(Device).filter(
                    Device.is_deleted == False,
                    Device.status != 'busy',
                    Device.last_seen < threshold
                ).all()
                
                if devices_to_update:
                    LOGGER.info(f"Found {len(devices_to_update)} stale device(s)")
                    for device in devices_to_update:
                        LOGGER.info(f"Marking device '{device.name}' (ID={device.id}) as offline")
                        device.status = 'offline'
                    db.commit()
                
            except Exception as e:
                LOGGER.error(f"Error in device status monitor: {e}")
                db.rollback()
            finally:
                db.close()
                
        except Exception as e:
            LOGGER.error(f"Unexpected error in monitor loop: {e}")
            await asyncio.sleep(5)


app = FastAPI()

app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(agent.router)
app.include_router(execute.router)
app.include_router(queue.router)


@app.on_event("startup")
async def startup_event():
    """Start background monitoring task when server starts."""
    LOGGER.info("Starting IoT server - launching device status monitor")
    asyncio.create_task(monitor_device_status())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown."""
    LOGGER.info("Shutting down IoT server")


@app.get("/")
def root():
    return {"message": "IoT server running"}