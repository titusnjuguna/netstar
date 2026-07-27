from pydantic import BaseModel,Field
from typing import List,Dict,Any,Optional
from datetime import datetime

class RouterCreate(BaseModel):
    name: str
    ip_address: str
    username: str
    password: str
    location: str
    till_number: str
    port: int = 8728
    hotspot_name: str = Field(..., examples=["Tano@Bora"])
    wan_interface: str = "ether1"
    wifi_country: str = "kenya"
    client : int


class ProductOut(BaseModel):
    id: str
    name: str
    price: int
    duration: int
    speedLimit: str
    dataLimit: str
    createdAt: datetime
    routerId: int
    hostname: Optional[str] = None


class RouterResponse(BaseModel):
    success: bool
    msg: str

class RouterDetail(BaseModel):
    success: bool
    msg : str
    data: Dict[str, Any]


class RouterOut(BaseModel):
    id: int
    name: str
    ipAddress: str
    port: int
    username: str
    status: str
    cpuLoad: int
    memoryUsage: int
    uptime: str
    activeUsers: int
    hotspotName: str
    tillNumber: str
    createdAt: Optional[datetime] = None
    routerUUID: str
    hostname: Optional[str] = None


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
    routerId: int


class ProductsListResponse(BaseModel):
    message: str
    products: List[ProductOut]


class ProductDetailResponse(BaseModel):
    message: str
    name: str
    location: Optional[str] = None
    product: ProductOut


class MessageResponse(BaseModel):
    message: str


class RouterRegistrationResponse(BaseModel):
    message: str
    routerId: int
    identity: str


class RegistrationScriptResponse(BaseModel):
    regToken: str
    script: str



class SetupScriptResponse(BaseModel):
    router_id: int
    tunnel_ip: str
    registration_token: str
    script: str
 
 
class RegisterCallbackRequest(BaseModel):
    token: str
    public_key: str
 
 
class RegisterCallbackResponse(BaseModel):
    status: str
    hub_public_key: str
    hub_endpoint_host: str
    hub_endpoint_port: int
    assigned_tunnel_ip: str
 
class WireGuardSet(BaseModel):
    public_key:str
    ip_address:str
    public_ip: Optional[str] = None



class PaginationMeta(BaseModel):
    total_items: int = Field(..., description="Total number of items in the database")
    total_pages: int = Field(..., description="Total number of pages")
    current_page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")

class NewProductsListResponse(BaseModel):
    message: str
    products: List[ProductOut]
    pagination: PaginationMeta 