from fastapi import APIRouter,Depends
from api.services.setup import check_mikrotik_status,set_speed_limit
from api.schemas.setup import RouterCreate,RouterResponse,RouterDTO,RouterResponser,RouterDetail,ProductCreate,ProductResponse,ProductsDTO,RouterResponserDTO
from sqlalchemy.orm import Session
from api.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from api.models.setup import RouterInfo,Products
from typing import List
from sqlalchemy.sql import desc
from librouteros import connect

router=APIRouter()

@router.post("/set/router", response_model=RouterResponse)
def set_router(routerInfo: RouterCreate, db: Session = Depends(get_db)):
    try:
        new_router = RouterInfo(
        ip_address=routerInfo.ip_address,
        password=routerInfo.password,
        user_name=routerInfo.username,
        location = routerInfo.location
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
    # for r in routers:
    #     print(r.products)
    try:
        total_count = db.query(RouterInfo).count()  # Get total count of routers
        router_responses = [RouterResponser(id=r.id, ip_address=r.ip_address, username=r.user_name,location=r.location,status='Online',products=[]) for r in routers]
        return RouterDTO(success=True, msg="Router settings retrieved successfully", total=total_count, routers=router_responses)
    except:
        return RouterDTO(success=True,msg="No router Found",total=0)

@router.get("/device/online/{id}")
def check_get_device_resource(id: int, db: Session = Depends(get_db)):
    router = db.query(RouterInfo).filter(RouterInfo.id == id).first()
    if router:
        host = router.ip_address
        port = router.port
        user = router.user_name
        password = router.password
        response= check_mikrotik_status(host=host,username=user,password=password,port=port)
        if response:
            cpu = None
            uptime = None
            for data in response:
                uptime=data.get('uptime')
                cpu = data.get('cpu-load')
            return RouterDetail(success=True,msg="Router is online",data={"cpu":cpu,"uptime":uptime,"status":"Online"})
        else:
            return RouterDetail(success=True,msg="Router is offline",data={"cpu":0,"uptime":0,"status":"Offline"})

@router.post("/create/products")
def create_products(product: ProductCreate,db: Session = Depends(get_db)):
 
    try:
        new_product = Products(
        product_name = product.product_name,
        product_category = product.product_category,
        download = product.download,
        upload = product.upload,
        price = product.price,
        billing_period = product.billing_period,
        product_status = product.product_status,
        router_id = product.router
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        router_id = product.router
        result = set_speed_limit(download_speed=product.download,upload_speed=product.upload,router_id=router_id,db=db)
        return RouterResponse(success=True, msg=f"Product created Successfully {result}.")
    except Exception as e:
        # Handle errors and return failure response
        return RouterResponse(success=False, msg=f"Error: {str(e)}")

@router.get("/get/products", response_model=ProductsDTO)
def get_all_routers(db: Session = Depends(get_db)):
    products = db.query(Products).order_by(desc(Products.id)).all()
    total_count = db.query(Products).count()  # Get total count of routers
    product_responses = [ProductResponse(id=p.id, product_name=p.product_name, product_category=p.product_category,download=p.download,upload = p.upload , price=p.price,billing_period=p.billing_period,product_status=p.product_status) for p in products]
    return ProductsDTO(success=True, msg="Products successfully", total=total_count, products=product_responses)

