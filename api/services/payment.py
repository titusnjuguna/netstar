import requests

def mpesa_authentication(user,passwd):
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    user_name = user
    password = passwd
    requests.post(url=url,)
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    payload = {}
    headers = {
    'Authorization': 'Basic dGVzdDE6MTIzNDU2Nzg5MA==',
    'Cookie': 'incap_ses_6547_2742146=RKZgLwLHc1fsj1xQA57bWkDBcmcAAAAAdcYZfyZVLVLmmF21xxVn2g==; visid_incap_2742146=pWohZ22ZR8ezxJHgaEpO6g3BcmcAAAAAQUIPAAAAAABRVT4Czdb6yltt25wA/aqt'
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    print(response.text)



def stk_push_request():
    {    
   "BusinessShortCode": "174379",    
   "Password": "MTc0Mzc5YmZiMjc5ZjlhYTliZGJjZjE1OGU5N2RkNzFhNDY3Y2QyZTBjODkzMDU5YjEwZjc4ZTZiNzJhZGExZWQyYzkxOTIwMTYwMjE2MTY1NjI3",    
   "Timestamp":"20160216165627",    
   "TransactionType": "CustomerPayBillOnline",    
   "Amount": "1",    
   "PartyA":"254708374149",    
   "PartyB":"174379",    
   "PhoneNumber":"254708374149",    
   "CallBackURL": "https://mydomain.com/pat",    
   "AccountReference":"Test",    
   "TransactionDesc":"Test"
}



def payment_callback_url():
    
{    
   "Body": {        
      "stkCallback": {            
         "MerchantRequestID": "29115-34620561-1",            
         "CheckoutRequestID": "ws_CO_191220191020363925",            
         "ResultCode": 0,            
         "ResultDesc": "The service request is processed successfully.",            
         "CallbackMetadata": {                
            "Item": [{                        
               "Name": "Amount",                        
               "Value": 1.00                    
            },                    
            {                        
               "Name": "MpesaReceiptNumber",                        
               "Value": "NLJ7RT61SV"                    
            },                    
            {                        
               "Name": "TransactionDate",                        
               "Value": 20191219102115                    
            },                    
            {                        
               "Name": "PhoneNumber",                        
               "Value": 254708374149                    
            }]            
         }        
      }    
   }
}
