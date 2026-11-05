
try:
    from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
except ImportError:
    FastMail = None
    MessageSchema = None
    ConnectionConfig = None
from dotenv import load_dotenv
import os

load_dotenv()

def send_email(email: str, message: str):
    conf = ConnectionConfig(
        MAIL_USERNAME= os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD= os.getenv("MAIL_PASSWORD"),
        MAIL_FROM= os.getenv("MAIL_FROM"),
        MAIL_PORT= os.getenv("MAIL_PORT"),
        MAIL_SERVER= os.getenv("MAIL_SERVER"),
        MAIL_STARTTLS= os.getenv("MAIL_STARTTLS") == "True",
        MAIL_SSL_TLS= os.getenv("MAIL_SSL_TLS") == "True",
    )

    message = MessageSchema(
        subject="Welcome",
        recipients=[email],
        body="<h1>Hello!</h1><br><p>Welcome to our service. Your credentials are as follows:{message}</p><br><p>{}</p>".format(message),
        subtype="html",
    )
    fm = FastMail(conf)
    fm.send_message(message)
    return {"message": "Email sent successfully"}

def send_sms(phone: str, message: str, db=None):
    try:
        from api.models.settings import SmsConfig
        sms_config = None
        if db:
            sms_config = db.query(SmsConfig).first()

        # If Africa's Talking is configured
        if sms_config and sms_config.gateway == "africas_talking" and sms_config.api_key and sms_config.api_username:
            import requests
            url = "https://api.africastalking.com/version1/messaging"
            headers = {
                "ApiKey": sms_config.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
            data = {
                "username": sms_config.api_username,
                "to": phone if phone.startswith("+") else f"+{phone}",
                "message": message,
            }
            if sms_config.sender_id:
                data["from"] = sms_config.sender_id
            requests.post(url, headers=headers, data=data, timeout=5)
        # If Twilio is configured
        elif sms_config and sms_config.gateway == "twilio" and sms_config.twilio_sid and sms_config.twilio_token:
            import requests
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sms_config.twilio_sid}/Messages.json"
            auth = (sms_config.twilio_sid, sms_config.twilio_token)
            data = {
                "To": phone if phone.startswith("+") else f"+{phone}",
                "From": sms_config.twilio_from,
                "Body": message
            }
            requests.post(url, auth=auth, data=data, timeout=5)

        print(f"[SMS DISPATCH] To: {phone} | Message: {message}")
        return True
    except Exception as e:
        print(f"[SMS ERROR] Failed to send SMS to {phone}: {e}")
        return False

def send_withdrawal_otp(phone: str, email: str, otp: str, amount: float, db=None):
    message = f"Your withdrawal verification OTP is: {otp}. It will expire in 10 minutes. Use this code to confirm your withdrawal of KES {amount:.2f}."
    send_sms(phone=phone, message=message, db=db)
    if email:
        try:
            from api.db.email import SendEmailService
            SendEmailService(to_address=email, subject="Withdrawal Verification OTP", body=message).send_email()
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send withdrawal OTP email to {email}: {e}")
