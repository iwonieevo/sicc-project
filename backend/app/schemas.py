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
    # device_id can be absent/null in edge cases; accept integer or null
    device_id: Optional[int] = None
    status: str
    result: Optional[str] = None
    