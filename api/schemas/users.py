from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    client: int

class UserLogin(BaseModel):
    username:str
    password:str
    

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    client_id : int

class OTPVerify(BaseModel):
    otp: str
    email: str