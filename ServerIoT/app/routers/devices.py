from fastapi import APIRouter

router = APIRouter()

devices = [
    {"device_id": 1, "name": "RasberryPi", "status": "offline", "last_seen" : None},
    {"device_id": 2, "name": "RasberryPi", "status": "offline", "last_seen" : None}
]

@router.get("/devices")
def get_devices():
    return devices