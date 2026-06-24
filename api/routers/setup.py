import json
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from api.services.setup import (
    check_mikrotik_status, get_router_live_stats, render_captive_portal_html,
    deploy_captive_portal, discover_routers,
    generate_reg_token, generate_ros_script,
)
from api.services.payment import stk_push_request
from api.schemas.setup import (
    RouterCreate, RouterResponse, RouterDetail, RouterOut, RoutersListResponse,
    RouterPingResponse, RouterFullCreate, HotspotPayRequest, DiscoveredRouter,
    DiscoverRoutersResponse, ProductCreate, ProductOut, ProductsListResponse,
    ProductDetailResponse, MessageResponse,
    RouterRegistrationResponse, RegistrationScriptResponse,
)
from api.schemas.payment import GeneralResponse
from sqlalchemy.orm import Session
from api.db.session import get_db, SessionLocal
from api.models.setup import RouterInfo, Products
from api.services.auth import verify_token
from sqlalchemy.sql import desc

router=APIRouter(
    prefix="/api",  # Optional but recommended
    tags=["Setup"]
)

@router.post("/add/router", response_model=RouterResponse)
def set_router(routerInfo: RouterCreate, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    try:
        new_router = RouterInfo(
        name=routerInfo.name,
        ip_address=routerInfo.ip_address,
        password=routerInfo.password,
        user_name=routerInfo.username,
        location = routerInfo.location,
        port=routerInfo.port,
        )
        db.add(new_router)
        db.commit()
        db.refresh(new_router)
        return RouterResponse(success=True, msg="Router successfully added.")
    except Exception as e:
        # Handle errors and return failure response
        return RouterResponse(success=False, msg=f"Error: {str(e)}")


@router.post("/v1/create/router")
def create_router(routerInfo: RouterFullCreate, _: dict = Depends(verify_token)):
    def event_stream():
        def sse(step, status, message, **extra):
            return f"{json.dumps({'step': step, 'status': status, 'message': message, **extra})}\n\n"
        db = SessionLocal()
        new_router = None
        try:
            yield sse("connect", "in_progress", "Connecting to MikroTik device...")
            stats = get_router_live_stats(
                host=routerInfo.ipAddress,
                username=routerInfo.username,
                password=routerInfo.password,
                port=8728,
            )
            if stats["status"] != "online":
                reason = stats.get("error") or "check IP address and credentials"
                yield sse("connect", "failed", f"Could not reach MikroTik — {reason}")
                return
            yield sse("connect", "done", "Connected to MikroTik device",
                      cpuLoad=stats["cpuLoad"], memoryUsage=stats["memoryUsage"], uptime=stats["uptime"])

            # Step 2: save to DB so we get the router ID needed for the captive portal payment URL
            yield sse("save", "in_progress", "Saving router configuration...")
            new_router = RouterInfo(
                name=routerInfo.name,
                ip_address=routerInfo.ipAddress,
                user_name=routerInfo.username,
                password=routerInfo.password,
                hotspot_name=routerInfo.hotspotName,
                till_number=routerInfo.tillNumber,
                port=8728,
                reg_token=generate_reg_token(),
            )
            try:
                db.add(new_router)
                db.commit()
                db.refresh(new_router)
            except Exception as e:
                db.rollback()
                yield sse("save", "failed", f"Failed to save router: {e}")
                return

            # Step 3: deploy captive portal using the real router ID
            yield sse("portal", "in_progress", "Deploying captive portal page...")
            html_content = render_captive_portal_html(
                hotspot_name=new_router.hotspot_name,
                router_id=new_router.id,
                till_number=new_router.till_number,
            )
            portal_ok, portal_msg = deploy_captive_portal(
                host=new_router.ip_address,
                username=new_router.user_name,
                password=new_router.password,
                html_content=html_content,
            )
            if not portal_ok:
                # Portal failed — roll back the DB save so no partial record is left
                db.delete(new_router)
                db.commit()
                new_router = None
                yield sse("portal", "failed", portal_msg)
                return
            yield sse("portal", "done", portal_msg)

            router_id = f"r{new_router.id}"
            yield sse("complete", "done", "Router setup complete", routerId=router_id, routerStatus="online")
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")

#initiate stk push request
#exclude from auth verification since this is called by the router script

@router.post("/hotspot/pay/{router_id}", response_model=GeneralResponse)
def hotspot_pay(router_id: int, payload: HotspotPayRequest, db: Session = Depends(get_db)):
    db_router = db.query(RouterInfo).filter(RouterInfo.reg_token== router_id).first()
    if not db_router:
        return GeneralResponse(message="Router not found", success=False, code=404)
    if not db_router.till_number:
        return GeneralResponse(message="Router has no till number configured", success=False, code=400)
    try:
        product_id = int(payload.productId)
    except ValueError:
        return GeneralResponse(message="Invalid package selected", success=False, code=400)
    product = db.query(Products).filter(Products.id == product_id).first()
    if not product:
        return GeneralResponse(message="Package not found", success=False, code=404)
    try:
        stk_push_request(amount=product.price, phone=payload.phone, till_number=db_router.till_number, db=db)
        return GeneralResponse(message="Payment request sent. Check your phone.", success=True, code=200)
    except Exception as e:
        return GeneralResponse(message=f"Error initiating payment: {e}", success=False, code=400)


@router.get("/v1/get/routers", response_model=RoutersListResponse)
def get_all_routers(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    routers = db.query(RouterInfo).all()
    router_responses = []
    for r in routers:
        stats = get_router_live_stats(host=r.ip_address, username=r.user_name, password=r.password, port=r.port)
        router_responses.append(RouterOut(
            id=r.id,
            name=r.name or "",
            ipAddress=r.ip_address,
            port=r.port or 8728,
            username=r.user_name,
            status=stats["status"],
            cpuLoad=stats["cpuLoad"],
            memoryUsage=stats["memoryUsage"],
            uptime=stats["uptime"],
            hotspotName=r.hotspot_name or "",
            tillNumber=r.till_number or "",
            createdAt=r.last_seen,
            routerUUID=r.reg_token or "",
            activeUsers=stats["activeUsers"]
        ))
    return RoutersListResponse(message="Routers fetched successfully", routers=router_responses)


@router.get("/v1/discover/routers", response_model=DiscoverRoutersResponse)
def discover_routers_endpoint(timeout: int = Query(5, ge=1, le=30), _: dict = Depends(verify_token)):
    devices = discover_routers(timeout=timeout)
    message = f"Discovered {len(devices)} device(s)" if devices else "No MikroTik devices found on the network"
    return DiscoverRoutersResponse(message=message, devices=[DiscoveredRouter(**d) for d in devices])


@router.get("/ping/router/{id}", response_model=RouterPingResponse)
def ping_router(id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_router = db.query(RouterInfo).filter(RouterInfo.id == id).first()
    if not db_router:
        raise HTTPException(status_code=404, detail="Router not found")
    stats = get_router_live_stats(host=db_router.ip_address, username=db_router.user_name,
                                   password=db_router.password, port=db_router.port)
    message = "Router is online" if stats["status"] == "online" else "Router is unreachable"
    return RouterPingResponse(
        message=message,
        status=stats["status"],
        cpuLoad=stats["cpuLoad"],
        memoryUsage=stats["memoryUsage"],
        uptime=stats["uptime"],
        activeUsers=stats["activeUsers"],
    )

@router.get("/online/device/{id}")
def check_get_device_resource(id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
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

@router.post("/v1/create/product", response_model=ProductDetailResponse)
def create_products(product: ProductCreate, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    new_product = Products(
        name=product.name,
        price=product.price,
        duration=product.duration,
        speed_limit=product.speedLimit,
        data_limit=product.dataLimit,
        router_id=product.routerId
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return ProductDetailResponse(
        message="Product created successfully",
        name = new_product.router.name if new_product.router else "Unknown",
        location = (new_product.router.location or "") if new_product.router else "",
        product=ProductOut(
            id=str(new_product.id),
            name=new_product.name,
            price=new_product.price,
            duration=new_product.duration,
            speedLimit=new_product.speed_limit,
            dataLimit=new_product.data_limit,
            createdAt=new_product.created_at,
        ),
    )


@router.put("/v1/update/product/{id}", response_model=ProductDetailResponse)
def update_product(id: int, product: ProductCreate, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_product = db.query(Products).filter(Products.id == id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.name = product.name
    db_product.price = product.price
    db_product.duration = product.duration
    db_product.speed_limit = product.speedLimit
    db_product.data_limit = product.dataLimit
    db.commit()
    db.refresh(db_product)
    return ProductDetailResponse(
        message="Product updated successfully",
        name = db_product.router.name if db_product.router else "Unknown",
        location = db_product.router.location if db_product.router else "Unknown",
        product=ProductOut(
            id=str(db_product.id),
            name=db_product.name,
            price=db_product.price,
            duration=db_product.duration,
            speedLimit=db_product.speed_limit,
            dataLimit=db_product.data_limit,
            createdAt=db_product.created_at,
        ),
    )


@router.delete("/v1/delete/product/{id}", response_model=MessageResponse)
def delete_product(id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_product = db.query(Products).filter(Products.id == id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return MessageResponse(message="Product deleted successfully")

@router.get("/v1/get/products", response_model=ProductsListResponse)
def get_all_products(
    db: Session = Depends(get_db),
    host: str = Query(None, description="Filter products by router IP address"),
):
    query = db.query(Products).order_by(desc(Products.id))
    if host:
        router = db.query(RouterInfo).filter(RouterInfo.hostname == host).first()
        if not router:
            return ProductsListResponse(message=f"No router found with hostname {host}", products=[])
        query = query.filter(Products.router_id == router.id)
    products = query.all()
    product_responses = [
        ProductOut(
            id=str(p.id),
            name=p.name,
            price=p.price,
            duration=p.duration or 0,
            speedLimit=p.speed_limit,
            dataLimit=p.data_limit or "Unlimited",
            createdAt=p.created_at,
            routerId=str(p.router_id) if p.router_id else 1,
        )
        for p in products
    ]
    return ProductsListResponse(message="Products fetched successfully", products=product_responses)



@router.post("/v1/register-router", response_model=RouterRegistrationResponse)
def register_router(
    request: Request,
    token: str = Form(...),
    identity: str = Form(""),
    board: str = Form(""),
    version: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Called by the MikroTik scheduler script on every reboot.
    No login required — the reg_token IS the authentication.

    What happens here:
      1. Find the router in the DB using the token
      2. Record the public IP the request came from (request.client.host)
         — this is how the VPS always knows the router's current public IP
      3. Update last_seen so the dashboard can show "online / last seen X"
    """
    db_router = db.query(RouterInfo).filter(RouterInfo.reg_token == token).first()
    if not db_router:
        raise HTTPException(status_code=404, detail="Unknown registration token")

    db_router.public_ip = request.client.host
    db_router.last_seen = datetime.utcnow()
    if identity:
        db_router.name = identity
    db.commit()

    return RouterRegistrationResponse(
        message="Router registered successfully",
        routerId=db_router.id,
        identity=identity or db_router.name or "",
    )


@router.get("/v1/router/{id}/registration-script", response_model=RegistrationScriptResponse)
def get_registration_script(
    id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """
    Returns the RouterOS script the admin copies and pastes into the
    MikroTik's System > Scheduler.

    The script contains the router's unique reg_token so only that
    specific router can call home with it.
    """
    from api.services.setup import API_BASE_URL
    db_router = db.query(RouterInfo).filter(RouterInfo.id == id).first()
    if not db_router:
        raise HTTPException(status_code=404, detail="Router not found")

    if not db_router.reg_token:
        db_router.reg_token = generate_reg_token()
        db.commit()

    script = generate_ros_script(db_router.reg_token, API_BASE_URL)
    return RegistrationScriptResponse(regToken=db_router.reg_token, script=script)
