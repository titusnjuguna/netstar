from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from api.db.session import get_db
from api.schemas.payment import PayRequest,PayResponse,PaymentConfigRequest,PaymentConfigResponse,GeneralResponse,SubscriptionOut,PaginationInfo,SubscriptionsListResponse
from api.models.payment import *
from api.models.setup import Products,RouterInfo
from api.services.payment import stk_push_request
from api.services.setup import create_hotspot_user,MikrotikOperation
from api.services.auth import verify_token
import json

router=APIRouter(
    prefix="/api", 
    tags=["payment"]
)


@router.get('/v1/get/subscriptions/{client_id}', response_model=SubscriptionsListResponse, tags=["payment"])
def get_subscriptions(client_id: int, page: int = Query(1, ge=1), db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    per_page = 20
    total_items = db.query(Subscription).filter(Subscription.is_active == True, Subscription.product.client_id == client_id).count()
    total_pages = max((total_items + per_page - 1) // per_page, 1)
    subscriptions = (
        db.query(Subscription).filter(Subscription.is_active == True, Subscription.product.client_id == client_id).
        .order_by(desc(Subscription.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    now = datetime.utcnow()
    subscription_responses = []
    for sub in subscriptions:
        package = sub.package
        latest_payment = (
            db.query(PaymentDisbursement)
            .filter(PaymentDisbursement.subscription_id == sub.id)
            .order_by(desc(PaymentDisbursement.payment_date))
            .first()
        )
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
                phone=latest_payment.phone if latest_payment else "",
                productName=package.name if package else "",
                startTime=sub.start_date,
                expiryTime=sub.end_date,
                dataUsed=0,
                dataCap=int(package.data_limit * 1024 * 1024) if package and package.data_limit else 0,
                status=status,
                ipAddress="",
            )
        )

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

    print(f"M-Pesa callback: checkout={checkout_id} result_code={result_code} desc={result_desc}")

    payment = db.query(HotspotPayments).filter(
        HotspotPayments.CheckoutRequestID == checkout_id
    ).first()

    if not payment:
        # Safaricom expects 200 regardless — log and ack
        print(f"Callback for unknown CheckoutRequestID: {checkout_id}")
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
    db.commit()
    print(f"Payment confirmed: receipt={receipt} checkout={checkout_id}")
    return GeneralResponse(message="ok", success=True, code=200)


@router.get('/hotspot/pay/status/{reference}', response_model=GeneralResponse, tags=["payment"])
def check_payment_status(reference: str, db: Session = Depends(get_db)):
    payment = db.query(HotspotPayments).filter(
        HotspotPayments.CheckoutRequestID == reference
    ).first()
    if not payment:
        return GeneralResponse(message="Payment not found", success=False, code=404)

    ref = payment.transaction_ref or ""
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
            MikrotikOperation(router=router,product=product).match_product_to_profile() 
            hotspot_password = ref[-8:]
            try:
                username,password = create_hotspot_user(
                    router=router,
                    phone=payment.phone,
                    duration_minutes=product.duration,
                    profile_name=product.name,
                    password=hotspot_password,
                )
                print(f"Hotspot user ready: {username} on router {router.name}")
                return GeneralResponse(
                    message="Payment successful",
                    success=True,
                    code=200,
                    payment_ref=ref,
                    hotspot_username=username,
                    hotspot_password=password,
                    login_url=f"http://10.10.10.1/login"
                )
            except Exception as e:
                import traceback
                print(f"Failed to create hotspot user: {e}\n{traceback.format_exc()}")
        return GeneralResponse(message="Payment successful", success=True, code=200)
    # transaction_ref still empty — STK sent but user hasn't acted yet
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

# @router.post('/order/{id}',response_model=GeneralResponse)
# def subscribe_package(id:int,detail:PayRequest,db:Session = Depends(get_db)):
#     phone = detail.phone
#     try:
#         product = db.query(Products).filter(Products.id==id).first()
#         product_price = product.price
#         router_id = product.router_id
#         router = db.query(RouterInfo).filter(RouterInfo.id==router_id).first()
#         till_number = router.till_number
#         #intiate an stk push
#         stk_push_request(amount=product_price,phone=phone,till_number=till_number,db=db)
#         # print("Wait for stk")
#         return GeneralResponse(message="Payment request sent",success=True,code=200)
#     except:
#         # print("Missing issue")
#         return GeneralResponse(message="Error in payment request",success=False,code=400)
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




    # pass
    # {    
    # "Body": {        
    #     "stkCallback": {            
    #         "MerchantRequestID": "29115-34620561-1",            
    #         "CheckoutRequestID": "ws_CO_191220191020363925",            
    #         "ResultCode": 0,            
    #         "ResultDesc": "The service request is processed successfully.",            
    #         "CallbackMetadata": {                
    #             "Item": [{                        
    #             "Name": "Amount",                        
    #             "Value": 1.00                    
    #             },                    
    #             {                        
    #             "Name": "MpesaReceiptNumber",                        
    #             "Value": "NLJ7RT61SV"                    
    #             },                    
    #             {                        
    #             "Name": "TransactionDate",                        
    #             "Value": 20191219102115                    
    #             },                    
    #             {                        
    #             "Name": "PhoneNumber",                        
    #             "Value": 254708374149                    
    #             }]            
    #         }        
    #     }    
    # }
    # }
