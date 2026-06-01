import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Device
from app.routers import agent, commands, devices, execute, secure
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

LOGGER = logging.getLogger(__name__)


def _sync_monitor_db_worker(interval: int):
    """
    Pure synchronous database operations worker.
    Runs isolated inside an OS threadpool thread via `asyncio.to_thread()`.
    """
    db = SessionLocal()
    
    try:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=interval)

        devices_to_update = (
            db.query(Device)
            .filter(Device.is_deleted == False, Device.status != "offline", Device.last_seen < threshold)
            .all()
        )

        if devices_to_update:
            LOGGER.info(f"Found {len(devices_to_update)} stale device(s)")
            for device in devices_to_update:
                LOGGER.info(f"Marking device '{device.name}' (ID={device.id}) as offline")
                device.status = "offline"
            db.commit()

    except Exception as e:
        LOGGER.error(f"Error in device status monitor DB operations: {e}")
        db.rollback()
    
    finally:
        db.close()


async def monitor_device_status_loop(interval: int):
    """
    Non-blocking async wrapper loop. Coordinates timing using `asyncio.sleep`
    and safely hands heavy database network I/O over to external thread workers.
    """
    if interval < 1:
        LOGGER.error(f"Invalid monitor interval '{interval}' seconds. Background loop aborted.")
        return

    LOGGER.info(f"Device health tracking initiated. Scan frequency: every {interval} seconds.")

    while True:
        try:
            await asyncio.sleep(interval)
            await asyncio.to_thread(_sync_monitor_db_worker, interval)
        except asyncio.CancelledError:
            LOGGER.info(
                "Device monitor execution loop caught cancel request. Halting thread worker assignments."
            )
            break
        except Exception as e:
            LOGGER.error(f"Unexpected error in monitor engine layer: {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles continuous orchestration steps matching server execution context lifetimes."""
    LOGGER.info("Starting IoT server engine - launching device status monitor task")

    monitor_interval = int(os.getenv("DEVICE_MONITOR_INTERVAL_SECONDS", "15"))
    monitor_task = asyncio.create_task(monitor_device_status_loop(monitor_interval))

    yield

    LOGGER.info("Shutting down IoT server - request cancellation of ongoing worker tasks")
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    LOGGER.info("Server shutdown operations completed successfully.")


app = FastAPI(lifespan=lifespan)

app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(agent.router)
app.include_router(execute.router)
app.include_router(secure.router)
app.include_router(secure.agent_iot_router)


@app.get("/")
def root():
    return {"message": "IoT server running"}
