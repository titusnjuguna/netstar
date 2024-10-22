from pydantic import BaseModel

class RouterCreate(BaseModel):
    ip_address:str
    username:str
    password:str