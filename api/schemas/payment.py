
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    payment_ref: Optional[str] = None
    hotspot_username: Optional[str] = None
    hotspot_password: Optional[str] = None


class SubscriptionOut(BaseModel):
    id: str
    mac: str
    phone: str
    productName: str
    startTime: datetime
    expiryTime: Optional[datetime] = None
    dataUsed: int
    dataCap: int
    status: str
    ipAddress: str


class PaginationInfo(BaseModel):
    page: int
    perPage: int
    totalItems: int
    totalPages: int


class SubscriptionsListResponse(BaseModel):
    message: str
    subscriptions: List[SubscriptionOut]
    pagination: PaginationInfo
