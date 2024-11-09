from pydantic import BaseModel
class RouterCreate(BaseModel):
    ip_address:str
    username:str
    password:str

class RouterResponse(BaseModel):
    success: bool
    msg: str
    total: int


from typing import List

class RouterResponser(BaseModel):
    id: int
    ip_address: str
    username: str
    # password: str

    class Config:
        orm_mode = True


class RouterDTO(BaseModel):
    success: bool
    msg: str
    total: int
    routers: List[RouterResponser]