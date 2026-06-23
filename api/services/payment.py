import os

from dotenv import load_dotenv
import requests
from api.models.payment import PaymentConfig 
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
    merchant = int(till_number)
    config = db.query(PaymentConfig).filter(PaymentConfig.merchant==merchant).first()
    if config:
        consumer_key= config.consumer_key
        consumer_secret= config.consumer_secret
        credentials = f"{consumer_key}:{consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        url = os.getenv("MPESA_AUTH_URL")
        response = requests.request("GET", url,headers = { 'Authorization': f'Basic {encoded_credentials}'})
        return response.text.encode('utf8')
    else:
        return None 
    
def stk_push_request(amount,phone,till_number,db):
    token=mpesa_authentication(db=db,till_number=till_number)
    session_ref= generate_secure_random_string(length=10)
    timestamp= datetime.now().strftime('%Y%m%d%H%M%S')
    passkey= os.getenv("MPESA_PASSKEY")
    password = f"{till_number}{passkey}{timestamp}"
    encoded_credentials = base64.b64encode(password.encode('utf-8')).decode('utf-8')
    headers = {'Content-Type': 'application/json','Authorization': f"'Bearer {token}'"}

    payload = {    
        "BusinessShortCode": till_number,    
        "Password": encoded_credentials,    
        "Timestamp": timestamp,    
        "TransactionType": "CustomerPayBillOnline",    
        "Amount": amount,    
        "PartyA":phone,    
        "PartyB": till_number,    
        "PhoneNumber": phone,    
        "CallBackURL": os.getenv("CALLBACK_URL"),    
        "AccountReference": f'Session:{session_ref}',    
        "TransactionDesc":f"Payment for hotspot {phone}"
        }
    stk_push_url = os.getenv("STK_PUSH_URL")
    response = requests.request("POST",stk_push_url,headers = headers, data = payload)
    return response.text.encode('utf8')




# {"Success":"True","Code":200,"message":"Success","customer":"Tito","limit":"1000","balance":0,"access":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzM3MzYwMDgwLCJqdGkiOiJhNzQ5NTQ4MTU4Njg0N2VjYjE5ZmRlYzUzN2U5OWUzNyIsInVzZXJfaWQiOjF9.XsuRk7Vi17QZUpcxO4YPi_mifkywQ1-HZlHkUQgFDlE","refresh":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTczNzQzNTY4MCwianRpIjoiOWIyZGU3YmU5MDQ4NDJiOWE4ZWI3NzI4NTRjY2ZiMDMiLCJ1c2VyX2lkIjoxfQ.kuL_xQ0JYWi50b2UmKbLVPVJYb9VYNsDah07qa44nSs"}
