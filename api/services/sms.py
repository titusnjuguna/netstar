
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
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