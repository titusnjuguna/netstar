from pydantic import BaseModel
from typing import Optional,List,Dict,Any
class RouterCreate(BaseModel):
    ip_address:str
    username:str
    password:str
    location:str

class ProductResponse(BaseModel):
    id: int
    product_name : str
    product_category : str
    download : int
    upload : int
    price : int
    billing_period : str
    product_status: str


class RouterResponse(BaseModel):
    success: bool
    msg: str
   
class RouterResponser(BaseModel):
    id: int
    ip_address: str
    username: str
    location: Optional[str] = None
    status: Optional[str] = None
    port: Optional[str]= '8287'
    products: Optional[List[ProductResponse]] = None

    class Config:
        from_attributes = True


class RouterDTO(BaseModel):
    success: bool
    msg: str
    total: int
    routers: List[RouterResponser]

class RouterDetail(BaseModel):
    success: bool
    msg : str
    data: Dict[str, Any]

class ProductCreate(BaseModel):
    product_name : str
    product_category : str
    download : int
    upload : int
    price : int
    billing_period : str
    product_status: str
    router : int


class ProductsDTO(BaseModel):
    success: bool
    msg: str
    total: int
    products: List[ProductResponse]

class RouterResponserDTO(RouterResponser):
    products: List[ProductResponse]