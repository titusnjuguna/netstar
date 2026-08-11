from .sms import send_email

def send_client_credentials(email, phone_number, password):
    # Implementation for sending client credentials
    pass

def send_otp_email(email, otp):
    try:
        send_email(
            email,
            subject="Your OTP Code",
            message=f"Your OTP code is: {otp}. It will expire in 10 minutes."
        )
    except Exception as e:
        print(f"Failed to send OTP email: {e}") 