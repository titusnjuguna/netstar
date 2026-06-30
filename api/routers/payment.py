from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from api.db.session import get_db
from api.schemas.payment import PayRequest,PayResponse,PaymentConfigRequest,PaymentConfigResponse,GeneralResponse,SubscriptionOut,PaginationInfo,SubscriptionsListResponse
from api.models.payment import *
from api.models.setup import Products,RouterInfo
from api.services.payment import stk_push_request
from api.services.auth import verify_token
import json
router=APIRouter(
    prefix="/api",  # Optional but recommended
    tags=["payment"]
)


@router.get('/v1/get/subscriptions', response_model=SubscriptionsListResponse, tags=["payment"])
def get_subscriptions(page: int = Query(1, ge=1), db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    per_page = 20
    total_items = db.query(Subscription).count()
    total_pages = max((total_items + per_page - 1) // per_page, 1)
    subscriptions = (
        db.query(Subscription)
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
            db.query(Payment)
            .filter(Payment.subscription_id == sub.id)
            .order_by(desc(Payment.payment_date))
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


@router.post('/callback',response_model=GeneralResponse,tags=["payment"])
async def payment_callback_url(request: Request, db: Session = Depends(get_db)):
    request_object =  await request.body()
    decoded_req_object = request_object.decode('utf-8').replace("'", '"')
    json_data = json.loads(decoded_req_object)
    # with open('TestingHot.json', 'w') as f:
    #     json.dump(json_data,f)
    try:
        db.query(HotspotPayments).filter(HotspotPayments.CheckoutRequestID==json_data['Body']['stkCallback']['CheckoutRequestID']).update({
        "transaction_ref": json_data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value'],
    })
    except:
        db.query(HotspotPayments).filter(HotspotPayments.phone==json_data['Body']['stkCallback']['CallbackMetadata']['Item'][3]['Value']).update({
            "transaction_ref": json_data['Body']['stkCallback']['CallbackMetadata']['Item'][1]['Value'],
        })
    #send whtsapp notification to user,to be added later

    return GeneralResponse(message='success',success=True,code=200)


@router.get('/hotspot/pay/status/{reference}',response_model=GeneralResponse,tags=["payment"])
def check_payment_status(reference:str,db:Session = Depends(get_db)):
    payment = db.query(HotspotPayments).filter(HotspotPayments.CheckoutRequestID==reference).first()
    if payment:
        if payment.transaction_ref != None:
            #add connection to mikrotik and create a user and password for auto login and respond for successfull connection
            
            return GeneralResponse(message="Payment successful",success=True,code=200)      
        else:
            return GeneralResponse(message="Payment failed",success=False,code=400)
    else:
        return GeneralResponse(message="Payment not found",success=False,code=404)
    


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
