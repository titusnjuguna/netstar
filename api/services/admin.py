from .sms import send_email
from api.db.email import SendEmailService

def send_client_credentials(email, phone_number, password):
    # Implementation for sending client credentials
    pass

def send_otp_email(email, otp):
    try:
        message=f"Your OTP code is: {otp}. It will expire in 10 minutes."
        SendEmailService(to_address=email,subject="Your OTP Code",body=message).send_email()
    except Exception as e:
        print(f"Failed to send OTP email: {e}") 