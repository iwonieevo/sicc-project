from typing import Optional

from pydantic import BaseModel, EmailStr

class UserRegister(BaseModel):
    email : EmailStr
    password: str

class UserLogin(BaseModel):
    email : EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
class UserResponse(BaseModel):
    email: EmailStr

class SimpleMessageRequest(BaseModel):
    agentId: str
    message: str

class ResultRequest(BaseModel):
    command_id: int
    device_id: str
    status: str
    result: Optional[str] = None
    