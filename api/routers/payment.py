from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from datetime import datetime,timedelta
from api.db.session import get_db
from api.schemas.payment import PayRequest,GenerateVoucherRequest,PaymentConfigRequest,PaymentConfigResponse,GeneralResponse,SubscriptionOut,PaginationInfo,SubscriptionsListResponse
from api.models.payment import *
from api.models.setup import Products,RouterInfo
from api.services.payment import stk_push_request
from api.services.setup import MikrotikOperation
from api.services.auth import verify_token
import json
import string,random

router=APIRouter(
    prefix="/api", 
    tags=["payment"]
)


@router.get('/v1/get/subscriptions/{client_id}', response_model=SubscriptionsListResponse, tags=["payment"])
def get_subscriptions(client_id: int, page: int = Query(1, ge=1), db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    per_page = 20
    base_query = (
        db.query(Subscription)
        .join(HotspotPayments, Subscription.payment_id == HotspotPayments.id)
        .join(Products, HotspotPayments.product_id == Products.id)
        .join(RouterInfo, Products.router_id == RouterInfo.id)
        .filter(Subscription.is_active == True, RouterInfo.client_id == client_id)
    )
    total_items = base_query.count()
    total_pages = max((total_items + per_page - 1) // per_page, 1)
    subscriptions = (
        base_query
        .options(joinedload(Subscription.payment).joinedload(HotspotPayments.products))
        .order_by(desc(Subscription.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    now = datetime.utcnow()
    subscription_responses = []
    for sub in subscriptions:
        package = sub.payment.products if sub.payment else None
        if not sub.is_active:
            status = "inactive"
        elif sub.end_date and sub.end_date < now:
            status = "expired"
        else:
            status = "active"

        subscription_responses.append(
            SubscriptionOut(
                id=f"s{sub.id}",
                mac="",
                phone=sub.phone or "",
                productName=package.name if package else "",
                startTime=sub.start_date,
                expiryTime=sub.end_date,
                dataUsed=0,
                dataCap=0,
                status="Active",
                ipAddress=""
            ))
    return SubscriptionsListResponse(
        message="Subscriptions fetched successfully",
        subscriptions=subscription_responses,
        pagination=PaginationInfo(page=page, perPage=per_page, totalItems=total_items, totalPages=total_pages),
    )

@router.post('/v1/b2c/callback', response_model=GeneralResponse, tags=["payment"])
def b2c_callback(request: Request, db: Session = Depends(get_db)):
    try:
        json_data = request.json()
    except Exception:
        raw = request.body()
        json_data = json.loads(raw.decode('utf-8'))
    print(f"B2C Callback received: {json_data}")
    conversation_id = json_data.get("Result", {}).get("OriginatorConversationID")
    result_code = json_data.get("Result", {}).get("ResultCode")
    payment = db.query(PaymentDisbursement).filter(
        PaymentDisbursement.conversation_id == conversation_id
    ).first()
    if not payment:
        print(f"Callback for unknown ConversationID: {conversation_id}")
        return GeneralResponse(message=f"Callback for unknown ConversationID: {conversation_id}", success=True, code=200)
    payment.success = True if result_code == 0 else False
    payment.transaction_ref = json_data.get("Result", {}).get("TransactionID", "")
    payment.payment_date = datetime.utcnow()
    db.commit()
    return GeneralResponse(message="B2C callback received", success=True, code=200)


@router.post('/payment/callback', response_model=GeneralResponse, tags=["payment"])
async def payment_callback_url(request: Request, db: Session = Depends(get_db)):
    try:
        json_data = await request.json()
    except Exception:
        raw = await request.body()
        json_data = json.loads(raw.decode('utf-8'))

    stk = json_data.get("Body", {}).get("stkCallback", {})
    checkout_id = stk.get("CheckoutRequestID")
    result_code = stk.get("ResultCode")
    result_desc = stk.get("ResultDesc", "")
    paybill_balance = stk.get("PaybillBalance",0)

    payment = db.query(HotspotPayments).filter(
        HotspotPayments.CheckoutRequestID == checkout_id
    ).first()

    if not payment:
        # Safaricom expects 200 regardless — log and ack
        return GeneralResponse(message="ok", success=True, code=200)

    if result_code != 0:
        # User cancelled, insufficient funds, timeout, etc.
        payment.transaction_ref = f"FAILED:{result_code}:{result_desc}"
        db.commit()
        return GeneralResponse(message="ok", success=True, code=200)

    # Extract metadata by Name — order-independent and safe
    items = {
        item["Name"]: item.get("Value")
        for item in stk.get("CallbackMetadata", {}).get("Item", [])
    }
    receipt = str(items.get("MpesaReceiptNumber", ""))
    paid_amount = items.get("Amount")

    # Fraud check: paid amount must be >= expected amount
    if paid_amount is not None and float(paid_amount) < float(payment.amount):
        payment.transaction_ref = f"FRAUD:paid={paid_amount},expected={payment.amount}"
    
        db.commit()
        print(f"FRAUD detected: checkout={checkout_id} paid={paid_amount} expected={payment.amount}")
        return GeneralResponse(message="ok", success=True, code=200)

    payment.transaction_ref = receipt
    payment.payment_date = datetime.utcnow()
    payment.paybill_balance = paybill_balance
    db.commit()
    return GeneralResponse(message="ok", success=True, code=200)


@router.get('/hotspot/pay/status/{reference}', response_model=GeneralResponse, tags=["payment"])
def check_payment_status(reference: str, db: Session = Depends(get_db)):
    payment = db.query(HotspotPayments).filter(
        HotspotPayments.CheckoutRequestID == reference).first()
    if not payment:
        return GeneralResponse(message="Payment not found", success=False, code=404)

    ref = payment.transaction_ref or ""
    phone = payment.phone
    paymentID = payment.id

    if ref.startswith("FAILED:"):
        _, code, *desc_parts = ref.split(":")
        desc = ":".join(desc_parts)
        return GeneralResponse(message=f"Payment failed: {desc}", success=False, code=400)
    if ref.startswith("FRAUD:"):
        return GeneralResponse(message="Payment amount mismatch — contact support", success=False, code=400)

    if ref:
        product = db.query(Products).filter(Products.id == payment.product_id).first()
        router = db.query(RouterInfo).filter(RouterInfo.id == product.router_id).first() if product else None
        if product and router:
            hotspot_password = ref[-8:]
            uptime = int(product.duration)
            router_name = router.name
            existing_sub = db.query(Subscription).filter(Subscription.payment_id == paymentID).first()
            if existing_sub:
                return GeneralResponse(
                    message="Payment successful",
                    success=True,
                    code=200,
                    payment_ref=ref,
                    hotspot_username=phone,
                    hotspot_password=hotspot_password,
                    login_url="http://10.10.10.1/login",)

            mkt = MikrotikOperation(router=router, product=product, phone=phone,
                                    uptime=uptime, hotspot_password=hotspot_password)
            mkt.match_product_to_profile()
            try:
                username, password = mkt.create_hotspot_user()
                now = datetime.utcnow()
                expire_date = now + timedelta(minutes=uptime)
                sub = Subscription(
                    device_identity="mobile",
                    phone=phone,
                    start_date=now,
                    end_date=expire_date,
                    is_active=True,
                    payment_id=paymentID,
                )
                db.add(sub)
                db.commit()
                return GeneralResponse(
                    message="Payment successful",
                    success=True,
                    code=200,
                    payment_ref=ref,
                    hotspot_username=username,
                    hotspot_password=password,
                    login_url="http://10.10.10.1/login",
                )
            except Exception as e:
                import traceback
                print(f"Failed to create hotspot user: {e}\n{traceback.format_exc()}")
                return GeneralResponse(message=f"Payment confirmed but router setup failed: {e}", success=False, code=500)

        return GeneralResponse(message="Payment successful", success=True, code=200)

    return GeneralResponse(message="Payment pending", success=False, code=202)
    

@router.post('/setup',response_model=None)
def add_payment_config(payment:PaymentConfigRequest,db:Session = Depends(get_db), _: dict = Depends(verify_token)):
    routerId = payment.router_id
    user = payment.user
    passwd= payment.password 
    consumer_key = payment.consumer_key
    consumer_secret = payment.consumer_secret 
    initiator_name = payment.initiator_name
    initiator_password = payment.initiator_password
    merchant = payment.merchant
    router_id = payment.router_id
    try:
        payconfig = db.query(PaymentConfig).filter(router_id=routerId).first()
        payconfig.user = user
        payconfig.password = passwd
        payconfig.consumer_key = consumer_key
        payconfig.merchant = merchant
        payconfig.router_id = router_id
        payconfig.save()
    except:
        #create payment setup
        new_payment = PaymentConfig(
            user=user,password=passwd,consumer_key=consumer_key,consumer_secret=consumer_secret,
            initiator_name=initiator_name,initiator_password= initiator_password,merchant=merchant,router_id=router_id)
        db.add(new_payment)
        db.commit()
        return PaymentConfigResponse(message="Config Added Successfully",success=True,code=200)


@router.post('/order/{id}', response_model=GeneralResponse)
def subscribe_package(id: int, detail: PayRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    phone = detail.phone
    stk_response=None
    try:
        # Add debugging prints
        print(f"Processing order for id: {id}, phone: {phone}")
        
        product = db.query(Products).filter(Products.id == id).first()
        print(f"Found product: {product}")
        if not product:
            return GeneralResponse(message="Product not found", success=False, code=404)
            
        product_price = product.price
        router_id = product.router_id
        print(f"Router ID: {router_id}")
        
        router = db.query(RouterInfo).filter(RouterInfo.id == router_id).first()
        print(f"Found router: {router}")
        if not router:
            return GeneralResponse(message="Router not found", success=False, code=404)
            
        till_number = router.till_number
        print(f"Till number: {till_number}")
        
        stk_response = stk_push_request(amount=product_price, phone=phone,till_number=till_number,db=db)
        print(f"STK Response: {stk_response}")
        
        return GeneralResponse(message="Payment request sent", success=True, code=200)
        
    except Exception as e:
        print(f"Detailed error: {str(e)}")
        import traceback
        print(traceback.format_exc())  # Print full stack trace
        return GeneralResponse(message=f"Error in payment request-{stk_response}", success=False, code=400)


@router.post('/api/hotspot/connect/mpesa', response_model=GeneralResponse, tags=["payment"])
def connect_hotspot_mpesa(request: PayRequest, db: Session = Depends(get_db)):
    phone = request.phone
    mpesa_ref = request.mpesa_ref
    payment = db.query(HotspotPayments).filter(HotspotPayments.transaction_ref == mpesa_ref,HotspotPayments.phone == phone).first()
    if not payment:
        return GeneralResponse(message="Payment not found", success=False, code=404)
    mtk = MikrotikOperation(router=payment.router, product=payment.products, phone=phone, uptime=payment.products.duration, hotspot_password=mpesa_ref[-8:])
    username,password = mtk.create_hotspot_user()
    return GeneralResponse(message="Payment request sent",
                           hotspot_username=username,
                           hotspot_password=password,
                           login_url="http://10.10.10.1/login",
                           success=True, code=200)


@router.post('/api/hotspot/connect/voucher', response_model=GeneralResponse, tags=["Voucher payment"])
def connect_hotspot_voucher(request: PayRequest, db: Session = Depends(get_db)):
    phone = request.phone
    voucher_code = request.voucher_code
    payment = db.query(HotspotPayments).filter(HotspotPayments.transaction_ref == voucher_code,HotspotPayments.phone == phone).first()
    if not payment:
        return GeneralResponse(message="Payment not found", success=False, code=404)
    mtk = MikrotikOperation(router=payment.router, product=payment.products, phone=phone, uptime=payment.products.duration, hotspot_password=voucher_code[-8:])
    mtk.create_hotspot_user()
    return GeneralResponse(message="Payment request sent", success=True, code=200)


@router.get('/api/generate/voucher/{client_id}', response_model=GeneralResponse, tags=["Voucher generation"])
def generate_voucher(client_id: int, request: GenerateVoucherRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    product_id = request.product_id
    phone = request.phone
    product = db.query(Products).filter(Products.id == product_id).first()
    if not product:
        return GeneralResponse(message="Product not found", success=False, code=404)
    router = db.query(RouterInfo).filter(RouterInfo.id == product.router_id).first()
    if not router:
        return GeneralResponse(message="Router not found", success=False, code=404)
    random_alphanum =  ''.join(random.choices(string.ascii_uppercase + string.digits,k=5))
    voucher_code = f"V{random_alphanum}{phone[-4:]}"
    # mtk = MikrotikOperation(router=router, product=product, phone=phone, uptime=product.duration, hotspot_password=voucher_code[-8:])
    # mtk.create_hotspot_user()
    vcr = VoucherPayment(phone=phone,
                         product_id=product_id,
                         status="unused",
                         voucher_code=voucher_code,
                         generated_date=datetime.utcnow())
    db.add(vcr)
    db.commit()
    return GeneralResponse(message="Voucher generated successfully", success=True,code=200)

@router.get('/api/get/vouchers/{client_id}', response_model=GeneralResponse, tags=["Voucher retrieval"])
def get_vouchers(client_id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    vouchers = db.query(VoucherPayment).filter(VoucherPayment.product.client_id == client_id).all()
    return GeneralResponse(message="Vouchers retrieved successfully", success=True, code=200, vouchers=vouchers)


@router.post('/api/client/withdraw', response_model=GeneralResponse, tags=["Withdraw"])
def client_withdraw(request: PayRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    phone = request.phone
    amount = request.amount
    client_id = request.client_id
    # Implement the logic to initiate a withdrawal for the client using the provided phone number and amount.
    # This could involve interacting with a payment gateway or service.
    # For now, we'll just return a success message.
    return GeneralResponse(message=f"Withdrawal of {amount} initiated for client {client_id} to phone {phone}", success=True, code=200)