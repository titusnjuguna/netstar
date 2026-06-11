from pydantic import BaseModel
from typing import List,Dict,Any,Optional
from datetime import datetime
class RouterCreate(BaseModel):
    name: str
    ip_address: str
    username: str
    password: str
    location: str
    port: int = 8728


class ProductOut(BaseModel):
    id: str
    name: str
    price: int
    duration: int
    speedLimit: str
    dataLimit: str
    createdAt: datetime


class RouterResponse(BaseModel):
    success: bool
    msg: str

class RouterDetail(BaseModel):
    success: bool
    msg : str
    data: Dict[str, Any]


class RouterOut(BaseModel):
    id: str
    name: str
    ipAddress: str
    port: int
    username: str
    status: str
    cpuLoad: int
    memoryUsage: int
    uptime: str
    activeUsers: int


class RoutersListResponse(BaseModel):
    message: str
    routers: List[RouterOut]


class RouterPingResponse(BaseModel):
    message: str
    status: str
    cpuLoad: int
    memoryUsage: int
    uptime: str
    activeUsers: int


class RouterFullCreate(BaseModel):
    name: str
    ipAddress: str
    username: str
    password: str
    hotspotName: str
    tillNumber: str


class HotspotPayRequest(BaseModel):
    phone: str
    productId: str


class DiscoveredRouter(BaseModel):
    ipAddress: str
    mac: Optional[str] = None
    identity: Optional[str] = None
    platform: Optional[str] = None
    board: Optional[str] = None
    version: Optional[str] = None
    method: str


class DiscoverRoutersResponse(BaseModel):
    message: str
    devices: List[DiscoveredRouter]

class ProductCreate(BaseModel):
    name: str
    price: int
    duration: int
    speedLimit: str
    dataLimit: str = "Unlimited"


class ProductsListResponse(BaseModel):
    message: str
    products: List[ProductOut]


class ProductDetailResponse(BaseModel):
    message: str
    product: ProductOut


class MessageResponse(BaseModel):
    message: str
