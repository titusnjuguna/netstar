import json
from datetime import datetime,timezone
from api.db import db
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from api.services.setup import * 
from api.services.payment import stk_push_request
from api.schemas.setup import * 
from api.schemas.payment import GeneralResponse
from sqlalchemy.orm import Session,joinedload
from api.db.session import get_db,SessionLocal
from api.models.setup import RouterInfo,Products
from api.services.auth import verify_token
from sqlalchemy.sql import desc
from sqlalchemy import Column, DateTime, Integer, String,select,desc
import math

router=APIRouter(prefix="/api",tags=["Router and Other Setup"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGIN_HTML_PATH = os.path.join(PROJECT_ROOT, "login.html")


@router.post("/v1/create/router")
def create_router(routerInfo: RouterCreate, _: dict = Depends(verify_token)):
    def event_stream():
        def sse(step, status, message, **extra):
            return f"{json.dumps({'step': step, 'status': status, 'message': message, **extra})}\n\n"
        db = SessionLocal()
        new_router = None
        try:
            yield sse("connect", "in_progress", "Connecting to MikroTik device...")
            stats = MikrotikOperation(router=routerInfo).get_router_live_stats()
           
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
                ip_address=routerInfo.ip_address,
                user_name=routerInfo.username,
                password=routerInfo.password,
                hotspot_name=routerInfo.hotspot_name,
                till_number=routerInfo.till_number,
                location=routerInfo.location,
                port=routerInfo.port,
                reg_token=generate_reg_token(),
                hostname=f'{routerInfo.hotspot_name.strip().lower()}.babybull.cc'
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
    db_router = db.query(RouterInfo).filter(RouterInfo.id==router_id).first()
    if not db_router:
        return GeneralResponse(message="Router not found", success=False, code=404)
    if not db_router.till_number:
        return GeneralResponse(message="Router has no till number configured", success=False, code=400)
    try:
        product_id = int(payload.productId)
    except ValueError:
        return GeneralResponse(message="Invalid package selected", success=False, code=400)
    product = db.query(Products).filter(Products.id == payload.productId).first()
    if not product:
        return GeneralResponse(message="Package not found", success=False, code=404)
    try:
        response = stk_push_request(amount=product.price, phone=payload.phone, till_number=db_router.till_number,product_id=product.id ,db=db)
        print(f"STK push request response API Query: {response}")
        if response.get("status_code") != 200:
            return GeneralResponse(message=f"Error initiating payment: {response.get('details')}", success=False, code=response.get("status_code"))
        return GeneralResponse(message="Payment request sent.Check your phone.",payment_ref = response.get("payment_ref"), success=True, code=200)
    except Exception as e:
        return GeneralResponse(message=f"Error initiating payment: {e}", success=False, code=400)


@router.get("/v1/get/routers", response_model=RoutersListResponse)
def get_all_routers(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    routers = db.query(RouterInfo).all()
    router_responses = []
    for r in routers:
        host = r.tunnel_ip or r.ip_address
        stats = MikrotikOperation(router=r).get_router_live_stats()
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
            activeUsers=stats["activeUsers"],
            hostname=r.hostname or ""
        ))
        if r.hostname and r.hostname != r.hostname.lower():
            r.hostname = r.hostname.lower()
            db.commit()
            db.refresh(r)
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
    stats = MikrotikOperation(router=db_router).get_router_live_stats()
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
def create_products(product: ProductCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    #check duration is greater than 1 if less convert to minutes and store in db
    if product.duration >= 1:
        new_duration = float(product.duration) * 60
  
    router = db.query(RouterInfo).filter(RouterInfo.id == product.routerId).first()
    if not router:
        raise HTTPException(status_code=404,detail="Router not found")

    new_product = Products(
        name=product.name,
        price=product.price,
        duration = new_duration,
        speed_limit=product.speedLimit,
        data_limit=product.dataLimit,
        router_id=int(product.routerId)
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    mikrotik_op = MikrotikOperation(router=router,product=new_product)
    background_tasks.add_task(mikrotik_op.match_product_to_profile)
    background_tasks.add_task(mikrotik_op.refresh_router_products)
    return ProductDetailResponse(
        message="Product created successfully",
        name = new_product.router.hotspot_name if new_product.router else "Unknown",
        location = (new_product.router.location or "") if new_product.router else "HotSpot",
        product=ProductOut(
            id=str(new_product.id),
            name=new_product.name,
            price=new_product.price,
            duration=new_product.duration,
            speedLimit=new_product.speed_limit,
            dataLimit=new_product.data_limit,
            createdAt=new_product.created_at,
            routerId=str(new_product.router_id) if new_product.router_id else 1,
            hostname=new_product.router.hostname if new_product.router else None    
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
            routerId=str(db_product.router_id) if db_product.router_id else 1,
            hostname=db_product.router.hostname if db_product.router else None
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
def get_all_products(background_tasks: BackgroundTasks,
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
    mikrotik_op = MikrotikOperation(router=router)
    background_tasks.add_task(mikrotik_op.fetch_hotspot_details)
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
            hostname=p.router.hostname if p.router else None
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



@router.post("/v1/generate/setup-script", response_model=SetupScriptResponse)
def generate_mikrotik_setup_script(
    req: RouterCreate,
    db: Session = Depends(get_db),
):
    tunnel_ip = allocate_tunnel_ip(db)
    api_username = req.username
    api_password = req.password
    registration_token = generate_reg_token()
    hostname = f'{req.hotspot_name}.wifi.babybull.cc'
    hostname = hostname.lower().replace(" ", "")
    new_router = RouterInfo(
        hotspot_name=req.hotspot_name,
        ip_address = req.ip_address,
        tunnel_ip=tunnel_ip,
        user_name=api_username,
        password=api_password,
        reg_token=registration_token,
        till_number = req.till_number,
        hostname = hostname
    )
  
    script = render_setup_script(
        router_id=new_router.id,
        req=req,
        tunnel_ip=tunnel_ip,
        api_username=api_username,
        api_password=api_password,
        registration_token=registration_token,
        wan_interface="ether1",
        hostname=hostname
    )
    db.add(new_router)
    db.commit()
    db.refresh(new_router)
 
    return SetupScriptResponse(
        router_id=new_router.id,
        tunnel_ip=tunnel_ip,
        registration_token=registration_token,
        script=script,
    )
 

 
@router.post("/v1/register/callback", response_model=RegisterCallbackResponse)
def register_callback(
    req: RegisterCallbackRequest,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(RouterInfo).where(RouterInfo.reg_token == req.token)
    ).scalar_one_or_none()
 
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown or expired registration token")
 
    # Idempotent: if it's already active with the same key, just re-confirm
    # rather than erroring — the router may retry this call on its own.
    if result.status == "active" and result.wg_public_key != req.public_key:
        raise HTTPException(
            status_code=409,
            detail="This router is already registered with a different key.",
        )
 
    apply_wireguard_peer(public_key=req.public_key, tunnel_ip=result.tunnel_ip)
 
    result.wg_public_key = req.public_key
    result.status = "active"
    result.registered_at = datetime.now(timezone.utc)
    db.commit()
 
    return RegisterCallbackResponse(
        status="active",
        hub_public_key=settings.HUB_PUBLIC_KEY,
        hub_endpoint_host=settings.HUB_ENDPOINT_HOST,
        hub_endpoint_port=settings.HUB_ENDPOINT_PORT,
        assigned_tunnel_ip=result.tunnel_ip,
    )
 
@router.get("/v1/get/router-ip")
def get_router_ip_address(db: Session = Depends(get_db)):
    ipaddress = allocate_tunnel_ip(db)
    if isinstance(ipaddress, str):
        return {"ip_address": ipaddress}
    else:
        return {"message": "Could not detect router IP"}


@router.post("/v1/set/wireguard")
def set_up_wireguard_router_to_backend(req: WireGuardSet, _: dict = Depends(verify_token), db: Session = Depends(get_db)):
    apply_wireguard_peer(public_key=req.public_key, tunnel_ip=req.ip_address)
    #set public facing ip address
    db_router = db.execute(select(RouterInfo).filter(RouterInfo.tunnel_ip == req.ip_address)).first()
    if db_router:
        db_router.public_ip = req.public_ip
        db.commit()
    return {"message": f"WireGuard peer {req.public_key} added with IP {req.ip_address}/32"}

@router.get("/v1/get/wireguard")
def get_wireguard_backend_to_router(_: dict = Depends(verify_token)):
    return {
        "hub_public_key": settings.HUB_PUBLIC_KEY,
        "hub_endpoint_host": settings.HUB_ENDPOINT_HOST,
        "hub_endpoint_port": settings.HUB_ENDPOINT_PORT,
        "hub_interface": settings.HUB_INTERFACE,
        "script": (
            f"/interface wireguard peers add interface={settings.HUB_INTERFACE} "
            f"public-key={settings.HUB_PUBLIC_KEY} "
            f"endpoint-address={settings.HUB_ENDPOINT_HOST} "
            f"endpoint-port={settings.HUB_ENDPOINT_PORT} "
            f"allowed-address=10.200.0.1/32 persistent-keepalive=25s"
        ),
    }


@router.post("/v1/deploy/login-page/{router_id}")
def launch_hotspot(router_id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_router = db.query(RouterInfo).filter(RouterInfo.id == router_id).first()
    if not db_router:
        raise HTTPException(status_code=404, detail="Router not found")

    host = db_router.tunnel_ip or db_router.ip_address
    if not host:
        raise HTTPException(status_code=400, detail="Router has no reachable address (tunnel_ip or ip_address)")

    if not os.path.isfile(LOGIN_HTML_PATH):
        raise HTTPException(status_code=500, detail=f"login.html not found at {LOGIN_HTML_PATH}")

    try:
        subprocess.run(
            [
                "sshpass", "-p", db_router.password,
                "scp",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=8",
                LOGIN_HTML_PATH,
                f"{db_router.user_name}@{host}:hotspot/login.html",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "No route to host" in stderr or "Connection closed" in stderr or "Connection refused" in stderr:
            raise HTTPException(
                status_code=503,
                detail=f"Router at {host} is unreachable — WireGuard tunnel is not established yet. "
                       "Run the setup script on the MikroTik first and wait for it to connect back.",
            )
        raise HTTPException(status_code=502, detail=f"scp failed: {stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Timed out connecting to {host} — tunnel may not be up yet")

    return {"message": f"login.html deployed to {host}:hotspot/login.html"}

@router.get("/v1/get/hotspot-details")
def get_hotspot_details(host: str = Query(..., description="Router hostname to fetch details"), db: Session = Depends(get_db)):
    router = db.query(RouterInfo).filter(RouterInfo.hostname == host.lower()).first()
    if not router:
        raise HTTPException(status_code=404, detail=f"No router found with hostname {host}")
    return {
        "hotspotName": router.hotspot_name,
        "location": router.location,
        "contact": router.phone_number,
        "advert": "For more info, visit our website at https://wifi.hotspot.babybull.cc",
        "Signature": "Powered by BabyBull Networks a Division Zenlow Ltd"
    }

@router.get("/v1/get/products", response_model=ProductsListResponse)
def get_products_by_router(host: str = Query(..., description="Router hostname to filter products"), db: Session = Depends(get_db)):
    router = db.query(RouterInfo).filter(RouterInfo.hostname == host.lower()).first()
    if not router:
        raise HTTPException(status_code=404, detail=f"No router found with hostname {host}")

    products = db.query(Products).filter(Products.router_id == router.id).order_by(desc(Products.id)).all()
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
            hostname = p.router.hostname if p.router else None )       for p in products
    ]
    return ProductsListResponse(message="Products fetched successfully", products=product_responses)

@router.get("/v1/get/client/products/{client}", response_model= NewProductsListResponse)
def get_products_with_routers(
    client : int,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (max 100)")):
    total_items = db.query(Products).count()
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 0
    offset = (page - 1) * page_size
    products = (
        db.query(Products)
        .join(RouterInfo, Products.router_id == RouterInfo.id)
        .filter(RouterInfo.client_id == client)
        .options(joinedload(Products.router))
        .order_by(desc(Products.id))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    product_responses = [
        ProductOut(
            id=str(p.id),
            name=p.name,
            price=p.price,
            duration=p.duration or 0,
            speedLimit=p.speed_limit,
            dataLimit=p.data_limit or "Unlimited",
            createdAt=p.created_at,
            routerId=int(p.router_id) if p.router_id else 0,
            hostname=p.router.hostname if p.router else None
        )
        for p in products
    ]
    return NewProductsListResponse(
        message="Products fetched successfully",
        products=product_responses,
        pagination=PaginationMeta(
            total_items=total_items,
            total_pages=total_pages,
            current_page=page,
            page_size=page_size
        )
    )

@router.delete("/v1/delete/router/{id}", response_model=MessageResponse)
def delete_router(id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_router = db.query(RouterInfo).filter(RouterInfo.id == id).first()
    if not db_router:
        raise HTTPException(status_code=404, detail="Router not found")
    db.delete(db_router)
    db.commit()
    return MessageResponse(message="Router deleted successfully")