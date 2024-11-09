from fastapi import APIRouter,Depends
from .service import add_router_info
from .schema import RouterCreate,RouterResponse,RouterDTO,RouterResponser
from sqlalchemy.orm import Session
from api.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from .models import RouterInfo
from typing import List
router=APIRouter()


@router.post("/set/router", response_model=RouterResponse)
def set_router(routerInfo: RouterCreate, db: Session = Depends(get_db)):
    try:
        new_router = RouterInfo(
        ip_address=routerInfo.ip_address,
        password=routerInfo.password,
        user_name=routerInfo.username
        )
        db.add(new_router)
        db.commit()
        db.refresh(new_router)
        return RouterResponse(success=True, msg="Router successfully added.")
    except Exception as e:
        # Handle errors and return failure response
        return RouterResponse(success=False, msg=f"Error: {str(e)}")

@router.get("/get/routers", response_model=RouterDTO)
def get_all_routers(db: Session = Depends(get_db)):
    routers = db.query(RouterInfo).all()
    total_count = db.query(RouterInfo).count()  # Get total count of routers
    router_responses = [RouterResponser(id=r.id, ip_address=r.ip_address, username=r.user_name) for r in routers]
    return RouterDTO(success=True, msg="Router settings retrieved successfully", total=total_count, routers=router_responses)
  