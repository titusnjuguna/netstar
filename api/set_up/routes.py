from fastapi import APIRouter,Depends
from .service import add_router_info
from .schema import RouterCreate
from sqlalchemy.orm import Session
from api.db.session import get_db

router=APIRouter()

@router.post("/set/router")
def set_router(routerInfo: RouterCreate,db:Session=Depends(get_db)):
    return add_router_info(routerInfo,db)