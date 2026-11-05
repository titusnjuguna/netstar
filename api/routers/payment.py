import os
import json
import string, random, secrets
try:
    import requests
except ImportError:
    requests = None
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from api.db.session import get_db
from api.schemas.payment import (
    VoucherRequest, GetVouchersGeneralResponse, GetVouchersResponse,
    MPayRequest, PayRequest, GenerateVoucherRequest, PaymentConfigRequest,
    PaymentConfigResponse, GeneralResponse, SubscriptionOut, PaginationInfo,
    SubscriptionsListResponse, ClientWithdrawRequest, WithdrawOtpRequest,
    AccountDetailsResponse, WalletTransactionsResponse, TransactionItem
)
from api.models.payment import *
from api.models.setup import Products, RouterInfo
from api.models.admin import Clients
from api.models.users import User
from api.services.payment import stk_push_request
from api.services.setup import MikrotikOperation
from api.services.auth import verify_token
from api.services.sms import send_withdrawal_otp

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
        .filter(RouterInfo.client_id == client_id)
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

    now = datetime.now()
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
    payment.payment_date = datetime.now()
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
    payment.payment_date = datetime.now()
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
                    login_url="http://10.10.10.1/login/",)
            mkt = MikrotikOperation(router=router, product=product, phone=phone,
                                    uptime=uptime, hotspot_password=hotspot_password)
            mkt.match_product_to_profile()
            try:
                username,password = mkt.create_hotspot_user()
                now = datetime.now()
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
                    login_url="http://10.10.10.1/login",)
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
        stk_response = stk_push_request(amount=product_price, phone=phone,till_number=till_number,db=db)       
        return GeneralResponse(message="Payment request sent", success=True, code=200)
        
    except Exception as e:
        print(f"Detailed error: {str(e)}")
        import traceback
        print(traceback.format_exc())  # Print full stack trace
        return GeneralResponse(message=f"Error in payment request-{stk_response}", success=False, code=400)


@router.post('/hotspot/connect/mpesa', response_model=GeneralResponse, tags=["payment"])
def connect_hotspot_mpesa(request: MPayRequest, db: Session = Depends(get_db)):
    mpesa_ref = request.reference
    payment = db.query(HotspotPayments).filter(HotspotPayments.transaction_ref == mpesa_ref).first()
    if not payment:
        return GeneralResponse(message="Payment not found", success=False, code=404)
    router = payment.products.router
    mtk = MikrotikOperation(router=router,product=payment.products, phone=payment.phone, uptime=payment.products.duration, hotspot_password=mpesa_ref[-8:])
    username,password = mtk.create_hotspot_user()
    return GeneralResponse(message="Payment request sent",
                           hotspot_username=username,
                           hotspot_password=password,
                           login_url="http://10.10.10.1/login",
                           success=True, code=200)


@router.post('/hotspot/connect/voucher', response_model=GeneralResponse, tags=["Voucher payment"])
def connect_hotspot_voucher(request:VoucherRequest, db: Session = Depends(get_db)):
    voucher_code = request.voucher
    payment = db.query(VoucherPayment).filter(VoucherPayment.voucher_code==voucher_code,VoucherPayment.status=="unused").first()
    
    if not payment:
        return GeneralResponse(message="Voucher already redeemed", success=False, code=404)
    product = db.query(Products).filter(Products.id==payment.product_id).first()
    phone = payment.phone
    mtk = MikrotikOperation(router=product.router, product=product, phone=phone, uptime=product.duration, hotspot_password=voucher_code)
    username,password = mtk.create_hotspot_user()
    payment.status="used"
    db.commit()
    print(f'{username}-{password}')
    return GeneralResponse(message="Payment request sent",
                               hotspot_username=username,
                               hotspot_password=password,
                               login_url="http://10.10.10.1/login",
                               success=True, code=200)


@router.post('/v1/generate/voucher/{client_id}', response_model=GeneralResponse, tags=["Voucher generation"])
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
    # mtk = MikrotikOperation(router=router, product=product, phone=phone, uptime=product.duration,hotspot_password=voucher_code)
    # mtk.create_hotspot_user()
    vcr = VoucherPayment(phone=phone,
                         product_id=product_id,
                         status="unused",
                         voucher_code=voucher_code,
                         generated_date=datetime.now())
    db.add(vcr)
    db.commit()
    return GeneralResponse(message="Voucher generated successfully", success=True,code=200)

@router.get('/v1/get/vouchers/{client_id}', response_model=GetVouchersGeneralResponse, tags=["Voucher retrieval"])
def get_vouchers(client_id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    vouchers = db.query(VoucherPayment).join(VoucherPayment.products).join(Products.router).filter(RouterInfo.client_id == client_id).all()
    return GetVouchersGeneralResponse(message="Vouchers retrieved successfully", success=True, code=200, vouchers=vouchers)


@router.get('/v1/get/account-details/{client_id}', response_model=AccountDetailsResponse, tags=["Account details"])
@router.get('/get/account-details/{client_id}', response_model=AccountDetailsResponse, tags=["Account details"])
@router.get('/wallet/summary/{client_id}', response_model=AccountDetailsResponse, tags=["Account details"])
@router.get('/v1/wallet/summary/{client_id}', response_model=AccountDetailsResponse, tags=["Account details"])
def get_account_details(client_id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    client = db.query(Clients).filter(Clients.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    routers = db.query(RouterInfo).filter(RouterInfo.client_id == client_id).all()
    router_ids = [r.id for r in routers]
    total_routers = len(routers)

    products = db.query(Products).filter(Products.router_id.in_(router_ids)).all() if router_ids else []
    product_ids = [p.id for p in products]

    total_revenue = 0.0
    if product_ids:
        total_revenue = (
            db.query(func.sum(HotspotPayments.amount))
            .filter(HotspotPayments.product_id.in_(product_ids))
            .scalar()
        ) or 0.0

    client_users = db.query(User).filter(User.client_id == client_id).all()
    user_ids = [u.id for u in client_users]
    total_withdrawn = 0.0
    pending_withdrawn = 0.0
    if user_ids:
        total_withdrawn = (
            db.query(func.sum(PaymentDisbursement.amount))
            .filter(PaymentDisbursement.user_id.in_(user_ids), PaymentDisbursement.success == True)
            .scalar()
        ) or 0.0

        pending_withdrawn = (
            db.query(func.sum(PaymentDisbursement.amount))
            .filter(PaymentDisbursement.user_id.in_(user_ids), PaymentDisbursement.success == False)
            .scalar()
        ) or 0.0

    available_balance = max(0.0, float(total_revenue) - float(total_withdrawn) - float(pending_withdrawn))

    data_dict = {
        "client_id": client.id,
        "client_name": client.name,
        "email": client.email,
        "phone_number": client.phone_number,
        "currency": "KES",
        "balance": round(available_balance, 2),
        "available_balance": round(available_balance, 2),
        "pending_balance": round(pending_withdrawn, 2),
        "pendingBalance": round(pending_withdrawn, 2),
        "total_revenue": round(float(total_revenue), 2),
        "total_withdrawn": round(float(total_withdrawn), 2),
        "total_routers": total_routers,
    }

    return AccountDetailsResponse(
        message="Account details retrieved successfully",
        success=True,
        code=200,
        currency="KES",
        balance=round(available_balance, 2),
        available_balance=round(available_balance, 2),
        pending_balance=round(pending_withdrawn, 2),
        pendingBalance=round(pending_withdrawn, 2),
        total_revenue=round(float(total_revenue), 2),
        total_withdrawn=round(float(total_withdrawn), 2),
        total_routers=total_routers,
        client_id=client.id,
        client_name=client.name,
        email=client.email,
        phone_number=client.phone_number,
        data=data_dict
    )


def process_withdrawal(client_id: int, amount: float, db: Session, phone: Optional[str] = None, otp: Optional[str] = None):
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    client = db.query(Clients).filter(Clients.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if amount is None or float(amount) <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be greater than zero")

    # Destination phone: consider the admin phone number from client profile
    target_phone = client.phone_number or (phone.strip() if phone else None)
    if not target_phone or not target_phone.strip():
        raise HTTPException(status_code=400, detail="Admin phone number not found for this client")

    clean_phone = target_phone.strip().replace(" ", "").replace("+", "").replace("-", "")
    if clean_phone.startswith("0"):
        clean_phone = "254" + clean_phone[1:]
    elif not clean_phone.startswith("254") and len(clean_phone) == 9:
        clean_phone = "254" + clean_phone

    # Calculate available balance
    routers = db.query(RouterInfo).filter(RouterInfo.client_id == client_id).all()
    router_ids = [r.id for r in routers]
    products = db.query(Products).filter(Products.router_id.in_(router_ids)).all() if router_ids else []
    product_ids = [p.id for p in products]

    total_revenue = 0.0
    if product_ids:
        total_revenue = (
            db.query(func.sum(HotspotPayments.amount))
            .filter(HotspotPayments.product_id.in_(product_ids))
            .scalar()
        ) or 0.0

    client_users = db.query(User).filter(User.client_id == client_id).all()
    user_ids = [u.id for u in client_users]
    total_withdrawn = 0.0
    pending_withdrawn = 0.0
    if user_ids:
        total_withdrawn = (
            db.query(func.sum(PaymentDisbursement.amount))
            .filter(PaymentDisbursement.user_id.in_(user_ids), PaymentDisbursement.success == True)
            .scalar()
        ) or 0.0

        pending_withdrawn = (
            db.query(func.sum(PaymentDisbursement.amount))
            .filter(PaymentDisbursement.user_id.in_(user_ids), PaymentDisbursement.success == False)
            .scalar()
        ) or 0.0

    available_balance = max(0.0, float(total_revenue) - float(total_withdrawn) - float(pending_withdrawn))

    if float(amount) > available_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds available balance. Available balance: KES {available_balance:.2f}"
        )

    # Locate the admin user record for this client to manage OTP
    admin_user = (
        db.query(User)
        .filter(User.client_id == client_id)
        .order_by(User.is_superuser.desc())
        .first()
    )

    # If OTP is not provided, generate OTP, send it to admin phone/email, and prompt user
    if not otp:
        otp_code = str(random.randint(100000, 999999))
        if admin_user:
            admin_user.otp = otp_code
            admin_user.otp_expiration = datetime.now(timezone.utc) + timedelta(minutes=10)
            db.commit()
            db.refresh(admin_user)

        # Dispatch OTP via SMS to admin phone and via email
        send_withdrawal_otp(phone=clean_phone, email=client.email, otp=otp_code, amount=float(amount), db=db)

        return GeneralResponse(
            message=f"A verification OTP has been sent to the admin phone number ({clean_phone}). Please enter the OTP to confirm your withdrawal.",
            success=True,
            code=200,
            otp_required=True,
            phone=clean_phone
        )

    # Verify provided OTP
    if not admin_user or not admin_user.otp:
        raise HTTPException(status_code=400, detail="No active withdrawal OTP found. Please request a new OTP.")

    expiry = admin_user.otp_expiration
    if expiry:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new OTP.")

    if str(admin_user.otp).strip() != str(otp).strip():
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please try again.")

    # OTP validated successfully: clear it
    admin_user.otp = None
    admin_user.otp_expiration = None
    db.commit()

    conversation_id = f"WD_{secrets.token_hex(12)}"
    primary_user_id = admin_user.id if admin_user else None

    # Check if router payment config exists for B2C
    payment_config = None
    if router_ids:
        payment_config = db.query(PaymentConfig).filter(PaymentConfig.router_id.in_(router_ids)).first()

    b2c_success = False
    owner_payment_url = os.getenv("OWNER_PAYMENT_URL")
    if payment_config and owner_payment_url and requests:
        try:
            b2c_payload = {
                "OriginatorConversationID": conversation_id,
                "InitiatorName": payment_config.user,
                "SecurityCredential": payment_config.password,
                "CommandID": "BusinessPayment",
                "Amount": float(amount),
                "PartyA": payment_config.merchant,
                "PartyB": clean_phone,
                "Remarks": f"Withdrawal for {client.name}",
                "QueueTimeOutURL": os.getenv("CALLBACK_URL", "https://api.net.babybull.cc/api/v1/b2c/callback"),
                "ResultURL": os.getenv("CALLBACK_URL", "https://api.net.babybull.cc/api/v1/b2c/callback"),
            }
            res = requests.post(owner_payment_url, json=b2c_payload, timeout=10)
            if res.status_code == 200 and res.json().get("ResponseCode") == "0":
                b2c_success = False  # Pending callback confirmation from Safaricom
            else:
                b2c_success = True
        except Exception as e:
            print(f"B2C request exception: {e}")
            b2c_success = True
    else:
        b2c_success = True

    new_disbursement = PaymentDisbursement(
        user_id=primary_user_id,
        amount=float(amount),
        payment_date=datetime.now(),
        phone=clean_phone,
        transaction_ref=f"WITHDRAW:{conversation_id[:8]}",
        conversation_id=conversation_id,
        success=b2c_success
    )
    db.add(new_disbursement)
    db.commit()
    db.refresh(new_disbursement)

    return GeneralResponse(
        message=f"Withdrawal of KES {float(amount):.2f} processed successfully to admin phone {clean_phone}.",
        success=True,
        code=200,
        payment_ref=conversation_id,
        otp_required=False,
        phone=clean_phone
    )


@router.post('/v1/client/withdraw/request-otp', response_model=GeneralResponse, tags=["Withdraw"])
@router.post('/client/withdraw/request-otp', response_model=GeneralResponse, tags=["Withdraw"])
@router.post('/wallet/withdraw/request-otp', response_model=GeneralResponse, tags=["Withdraw"])
def request_withdrawal_otp(request: WithdrawOtpRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    cid = request.client_id or request.clientId
    return process_withdrawal(client_id=cid, amount=request.amount, db=db, otp=None)


@router.post('/wallet/withdraw/{client_id}/request-otp', response_model=GeneralResponse, tags=["Withdraw"])
@router.post('/v1/wallet/withdraw/{client_id}/request-otp', response_model=GeneralResponse, tags=["Withdraw"])
def wallet_request_withdrawal_otp(client_id: int, request: WithdrawOtpRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    return process_withdrawal(client_id=client_id, amount=request.amount, db=db, otp=None)


@router.post('/v1/client/withdraw', response_model=GeneralResponse, tags=["Withdraw"])
@router.post('/client/withdraw', response_model=GeneralResponse, tags=["Withdraw"])
def client_withdraw(request: ClientWithdrawRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    cid = request.client_id or request.clientId
    return process_withdrawal(client_id=cid, amount=request.amount, db=db, phone=request.phone, otp=request.otp)


@router.post('/wallet/withdraw/{client_id}', response_model=GeneralResponse, tags=["Withdraw"])
@router.post('/v1/wallet/withdraw/{client_id}', response_model=GeneralResponse, tags=["Withdraw"])
def wallet_withdraw(client_id: int, request: ClientWithdrawRequest, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    return process_withdrawal(client_id=client_id, amount=request.amount, db=db, phone=request.phone, otp=request.otp)


@router.get('/wallet/transactions/{client_id}', response_model=WalletTransactionsResponse, tags=["Wallet"])
@router.get('/v1/wallet/transactions/{client_id}', response_model=WalletTransactionsResponse, tags=["Wallet"])
def get_wallet_transactions(
    client_id: int,
    page: int = Query(1, ge=1),
    perPage: int = Query(10, ge=1),
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    routerId: Optional[str] = None,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    client = db.query(Clients).filter(Clients.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    routers_query = db.query(RouterInfo).filter(RouterInfo.client_id == client_id)
    if routerId and routerId != 'all':
        try:
            routers_query = routers_query.filter(RouterInfo.id == int(routerId))
        except ValueError:
            pass
    routers = routers_query.all()
    router_map = {r.id: r.name for r in routers}
    router_ids = list(router_map.keys())

    # 1. HotspotPayments (credits)
    credit_items = []
    if router_ids:
        hp_query = (
            db.query(HotspotPayments, Products.router_id)
            .join(Products, HotspotPayments.product_id == Products.id)
            .filter(Products.router_id.in_(router_ids))
        )
        if dateFrom:
            try:
                dt_from = datetime.fromisoformat(dateFrom)
                hp_query = hp_query.filter(HotspotPayments.payment_date >= dt_from)
            except Exception:
                pass
        if dateTo:
            try:
                dt_to = datetime.fromisoformat(dateTo)
                hp_query = hp_query.filter(HotspotPayments.payment_date <= dt_to)
            except Exception:
                pass

        for hp, r_id in hp_query.all():
            status = "completed"
            if hp.transaction_ref and hp.transaction_ref.startswith("FAILED"):
                status = "failed"
            elif not hp.transaction_ref:
                status = "pending"
            credit_items.append({
                "id": f"c_{hp.id}",
                "date": hp.payment_date or hp.created_at,
                "type": "credit",
                "description": f"Hotspot payment {hp.phone or ''} ({hp.transaction_ref or ''})",
                "routerId": str(r_id),
                "routerName": router_map.get(r_id, "Unknown"),
                "amount": float(hp.amount or 0),
                "status": status
            })

    # 2. PaymentDisbursements (debits)
    debit_items = []
    client_users = db.query(User).filter(User.client_id == client_id).all()
    user_ids = [u.id for u in client_users]
    if user_ids and (not routerId or routerId == 'all'):
        pd_query = db.query(PaymentDisbursement).filter(PaymentDisbursement.user_id.in_(user_ids))
        if dateFrom:
            try:
                dt_from = datetime.fromisoformat(dateFrom)
                pd_query = pd_query.filter(PaymentDisbursement.payment_date >= dt_from)
            except Exception:
                pass
        if dateTo:
            try:
                dt_to = datetime.fromisoformat(dateTo)
                pd_query = pd_query.filter(PaymentDisbursement.payment_date <= dt_to)
            except Exception:
                pass

        for pd in pd_query.all():
            status = "completed" if pd.success else "pending"
            debit_items.append({
                "id": f"d_{pd.id}",
                "date": pd.payment_date or datetime.now(),
                "type": "debit",
                "description": f"Withdrawal to {pd.phone}",
                "routerId": None,
                "routerName": None,
                "amount": float(pd.amount or 0),
                "status": status
            })

    all_items = credit_items + debit_items
    all_items.sort(key=lambda x: x["date"] or datetime.min)

    # Compute running balance
    running_balance = 0.0
    for item in all_items:
        if item["status"] == "completed":
            if item["type"] == "credit":
                running_balance += item["amount"]
            else:
                running_balance -= item["amount"]
        item["balanceAfter"] = round(running_balance, 2)

    # Sort descending for display (most recent first)
    all_items.sort(key=lambda x: x["date"] or datetime.min, reverse=True)

    total_items = len(all_items)
    total_pages = max(1, (total_items + perPage - 1) // perPage)
    start_idx = (page - 1) * perPage
    paged_items = all_items[start_idx:start_idx + perPage]

    transaction_objs = [TransactionItem(**it) for it in paged_items]

    return WalletTransactionsResponse(
        message="Transactions retrieved successfully",
        success=True,
        code=200,
        transactions=transaction_objs,
        pagination=PaginationInfo(
            page=page,
            perPage=perPage,
            totalItems=total_items,
            totalPages=total_pages
        )
    )