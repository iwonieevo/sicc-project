from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class DeviceResponse(BaseModel):
    id: int
    name: str
    status: str
    last_seen: Optional[datetime] = None


class CommandParameterResponse(BaseModel):
    id: int
    name: str
    param_type: str
    is_required: bool
    default_value: Optional[str] = None
    description: Optional[str] = None


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


class ExecuteCommandRequest(BaseModel):
    device_id: int
    command_id: int
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ExecuteAnyCommandRequest(BaseModel):
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


class ResultCallbackRequest(BaseModel):
    queue_id: int
    is_error: bool
    result: Optional[str] = None


class QueueItemResponse(BaseModel):
    queue_id: int
    command_id: int
    command_name: str
    parameters: Optional[Dict[str, Any]] = None
    status: str
    queued_at: str
    can_cancel: bool 


class QueueCancelResponse(BaseModel):
    status: str
    device_id: int
    queue_id: int 