from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List


class RegisterRequest(BaseModel):
    name: str = Field(..., description="Agent hostname or identifier")


class RegisterResponse(BaseModel):
    device_id: int
    status: str


class CallbackRequest(BaseModel):
    queue_id: int
    is_error: bool
    result: Optional[str] = None


class ExecuteRequest(BaseModel):
    device_id: int
    command_id: int
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    queue_id: int


class DeviceResponse(BaseModel):
    id: int
    name: str
    status: str
    last_seen: Optional[datetime]
    registered_at: Optional[datetime]
    updated_at: Optional[datetime]


class CommandParameterResponse(BaseModel):
    id: int
    name: str
    param_type: str
    is_required: bool
    default_value: Optional[str]
    description: Optional[str]


class CommandResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    func_definition: str
    parameters: List[CommandParameterResponse]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class CommandStatusResponse(BaseModel):
    queue_id: int
    device_id: int
    command_id: int
    parameters: Optional[Dict[str, Any]]
    queued_at: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    is_error: Optional[bool]
    result: Optional[str]
    status: str


class PollCommandResponse(BaseModel):
    queue_id: int
    function_code: str
    parameters: Dict[str, Any]