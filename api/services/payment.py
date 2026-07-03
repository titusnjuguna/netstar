import os

from dotenv import load_dotenv
import requests
from api.models.payment import HotspotPayments, PaymentConfig 
from api.models.settings import MpesaConfig
from api.schemas.payment import PaymentConfigRequest, PaymentConfigResponse, PayRequest
from sqlalchemy.orm import Session
from api.db.session import get_db
from fastapi import Depends
import base64
from datetime import datetime
import secrets
import string
from requests.auth import HTTPBasicAuth
#get the .env variables

load_dotenv()

def generate_secure_random_string(length):
    characters = string.ascii_letters + string.digits
    random_string = ''.join(secrets.choice(characters) for _ in range(length))
    return random_string

def mpesa_authentication(till_number,db):
    merchant = str(till_number)
    config = db.query(MpesaConfig).filter(MpesaConfig.paybill_number==merchant).first()
    if config:
        consumer_key= config.consumer_key
        consumer_secret= config.consumer_secret
        credentials = f"{consumer_key}:{consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        url = os.getenv("MPESA_AUTH_URL")
        response = requests.request("GET", url,headers = { 'Authorization': f'Basic {encoded_credentials}'})
        print(f"MPESA Authentication response: {response.text}")
        return response.json().get("access_token")
    else:
        return None 
    
def stk_push_request(amount,phone,till_number,product_id,db):
    token=mpesa_authentication(db=db,till_number=till_number)
    session_ref= generate_secure_random_string(length=10)
    timestamp= datetime.now().strftime('%Y%m%d%H%M%S')
    passkey= os.getenv("MPESA_PASSKEY")
    password = f"{till_number}{passkey}{timestamp}"
    encoded_credentials = base64.b64encode(password.encode('utf-8')).decode('utf-8')
    headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {token}"}
    till_number = till_number
    payload = {
        "BusinessShortCode": till_number,
        "Password": encoded_credentials,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": till_number,
        "PhoneNumber": phone,
        "CallBackURL": os.getenv("CALLBACK_URL"),
        "AccountReference": f'Session:{session_ref}',
        "TransactionDesc": f"Payment for hotspot {phone}"
    }
    stk_push_url = os.getenv("STK_PUSH_URL")
    print(f"STK push request payload: {payload}")
    response = requests.request("POST", stk_push_url, headers=headers, json=payload)
    if response.json().get("ResponseCode") == "0":
        print(f"STK push request sent. Response: {response.text}")
        #add the payment record to the database
        CheckoutRequestID = response.json().get("CheckoutRequestID", "")
        new_payment = HotspotPayments(
            amount = amount,
            payment_date = datetime.utcnow(),
            phone = phone,
            transaction_ref = "",
            product_id = product_id,
            CheckoutRequestID = CheckoutRequestID,
            has_been_transferred = False
        )
        db.add(new_payment)
        db.commit()
        return {"message": "STK push request sent successfully", "details": response.text, "status_code": response.status_code}
    else:
        print(f"Error occurred while making STK push request: {response.text}")
        return {"error": "Failed to initiate STK push request", "details": response.text, "status_code": response.status_code}

# {"Success":"True","Code":200,"message":"Success","customer":"Tito","limit":"1000","balance":0,"access":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzM3MzYwMDgwLCJqdGkiOiJhNzQ5NTQ4MTU4Njg0N2VjYjE5ZmRlYzUzN2U5OWUzNyIsInVzZXJfaWQiOjF9.XsuRk7Vi17QZUpcxO4YPi_mifkywQ1-HZlHkUQgFDlE","refresh":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTczNzQzNTY4MCwianRpIjoiOWIyZGU3YmU5MDQ4NDJiOWE4ZWI3NzI4NTRjY2ZiMDMiLCJ1c2VyX2lkIjoxfQ.kuL_xQ0JYWi50b2UmKbLVPVJYb9VYNsDah07qa44nSs"}
