import os
import requests
import logging
from fastapi import APIRouter, HTTPException, Depends

from app.schemas import (
    CommandResponse,
    DeviceResponse,
    CommandStatusResponse,
    ExecuteCommandRequest,
    ExecuteCommandResponse,
    CommandCreateRequest,
    ResultCallbackRequest,
    QueueItemResponse,
    QueueCancelResponse,
)
from app.auth import get_current_user


IOT_SERVER_URL = os.getenv("IOT_SERVER_URL", "http://iot-server:7000")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["commands"])


def model_to_dict(model):
    """
    Convert a Pydantic model to a dictionary.
    """
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def build_server_url(path: str) -> str:
 
    return f"{IOT_SERVER_URL.rstrip('/')}{path}"


def forward_to_server(method: str, path: str, json_data=None, params=None):
    """
    Forward a request from the backend to the IoT server.
    Return the server response back to the frontend.
    """
    url = build_server_url(path)

    try:
        response = requests.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            timeout=10,
        )

        if response.status_code >= 400:
            try:
                error_data = response.json()
                detail = error_data.get("detail", error_data)
            except ValueError:
                detail = response.text or "Server error"

            raise HTTPException(
                status_code=response.status_code,
                detail=detail,
            )

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError:
            return {"message": response.text}

    except HTTPException:
        raise

    except requests.RequestException as e:
        logger.error(f"Failed to forward request to IoT server: {e}")
        raise HTTPException(
            status_code=503,
            detail="IoT server unavailable",
        )


@router.get("/devices", response_model=list[DeviceResponse])
def list_devices(
    current_user: dict = Depends(get_current_user),
):

    return forward_to_server(
        method="GET",
        path="/devices",
    )


@router.get("/commands", response_model=list[CommandResponse])
def list_commands(
    current_user: dict = Depends(get_current_user),
):

    return forward_to_server(
        method="GET",
        path="/commands",
    )


@router.post("/execute", response_model=ExecuteCommandResponse)
def execute_command(
    request: ExecuteCommandRequest,
    current_user: dict = Depends(get_current_user),
):

    response_data = forward_to_server(
        method="POST",
        path="/execute",
        json_data=model_to_dict(request),
    )

    if not response_data:
        raise HTTPException(status_code=502, detail="IoT server did not return a response")

    queue_id = response_data["queue_id"]

    return ExecuteCommandResponse(
        queue_id=queue_id,
        status_url=f"/api/status/{queue_id}",
    )


@router.get("/logs")
def get_execution_logs(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):

    return forward_to_server(
        method="GET",
        path="/logs",
        params={"limit": limit},
    )


@router.get("/status/{queue_id}", response_model=CommandStatusResponse)
def get_command_status(
    queue_id: int,
    current_user: dict = Depends(get_current_user),
):

    return forward_to_server(
        method="GET",
        path=f"/status/{queue_id}",
    )


@router.post("/commands", response_model=CommandResponse)
def create_command(
    request: CommandCreateRequest,
    current_user: dict = Depends(get_current_user),
):

    return forward_to_server(
        method="POST",
        path="/commands",
        json_data=model_to_dict(request),
    )


@router.post("/result")
def receive_result(request: ResultCallbackRequest):

    return forward_to_server(
        method="POST",
        path="/result",
        json_data=model_to_dict(request),
    )

@router.get("/devices/{device_id}/queue", response_model=list[QueueItemResponse])
def get_device_queue(
    device_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Get the queue for a selected device.
    """
    return forward_to_server(
        method="GET",
        path=f"/devices/{device_id}/queue",
    )

@router.post("/devices/{device_id}/queue/{queue_id}/cancel", response_model=QueueCancelResponse)
def cancel_queue_task(
    device_id: int,
    queue_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Cancel a queued command for a selected device.
    """
    return forward_to_server(
        method="POST",
        path=f"/devices/{device_id}/queue/{queue_id}/cancel",
    )