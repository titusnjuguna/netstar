
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool

class PayRequest(BaseModel):
    phone : str

class PayResponse(BaseModel):
    pass
    
class PaymentConfigRequest(BaseModel):
    user : str
    password : str
    consumer_key : str
    consumer_secret : str
    initiator_name: str
    initiator_password : str
    merchant : int
    router_id : int

class PaymentConfigResponse(BaseModel):
    message:str
    success: bool
    code: int

class GeneralResponse(BaseModel):
    message: str
    success: bool
    code: int
