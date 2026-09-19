import os
from dotenv import load_dotenv
import resend

load_dotenv()


class SendEmailService:
    def __init__(self, **kwargs):
        self.to_address = kwargs.get("to_address")
        self.subject = kwargs.get("subject")
        self.body = kwargs.get("body")

    def send_email(self, to_address=None, subject=None, body=None):
        if to_address is None:
            to_address = self.to_address
        if subject is None:
            subject = self.subject
        if body is None:
            body = self.body
        from_address = os.getenv("FROM_ADDRESS","no-reply@zenlow.co")
        api_key = os.getenv("RESEND_API_KEY")

        if not from_address:
            raise ValueError("FROM_ADDRESS environment variable is not set.")

        payload = {
            "from": from_address,
            "to": to_address,
            "subject": subject,
            "html": body,
        }
        return resend.Emails.send(payload)