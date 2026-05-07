from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


# Auth schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# Device schemas
class DeviceResponse(BaseModel):
    id: int
    name: str
    status: str
    last_seen: Optional[datetime] = None


# Command parameter schemas
class CommandParameterResponse(BaseModel):
    id: int
    name: str
    param_type: str
    is_required: bool
    default_value: Optional[str] = None
    description: Optional[str] = None

# Command schemas
class CommandResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parameters: List[CommandParameterResponse] = []


class CommandCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    python_code: str


class CommandUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    python_code: Optional[str] = None


# Execution schemas
class ExecuteCommandRequest(BaseModel):
    device_id: int
    command_id: int
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ExecuteCommandResponse(BaseModel):
    queue_id: int
    status_url: str = "/api/status/{queue_id}"


class CommandStatusResponse(BaseModel):
    queue_id: int
    device_id: int
    command_id: int
    parameters: Optional[Dict[str, Any]] = None
    status: str
    result: Optional[str] = None
    is_error: Optional[bool] = None
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# IoT Server callback schemas
class ResultCallbackRequest(BaseModel):
    queue_id: int
    is_error: bool
    result: Optional[str] = None


# Queue schemas
class QueueItemResponse(BaseModel):
    queue_id: int
    command_id: int
    command_name: str
    parameters: Optional[Dict[str, Any]] = None
    status: str
    can_delete: bool

class QueueDeleteResponse(BaseModel):
    status: str
    device_id: int
    queue_id: int