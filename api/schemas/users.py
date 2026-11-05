from pydantic import BaseModel, ConfigDict
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_superuser: Optional[bool] = False
    is_active: Optional[bool] = True
    client: Optional[int] = None
    client_id: Optional[int] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: Optional[bool] = False
    client_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class OTPVerify(BaseModel):
    otp: str
    email: str
