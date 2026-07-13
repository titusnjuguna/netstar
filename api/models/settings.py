from sqlalchemy import Column, Integer, String
from api.db.session import Base


class MpesaConfig(Base):
    __tablename__ = "mpesa_configs"
    id = Column(Integer, primary_key=True, index=True)
    environment = Column(String, default="sandbox")
    paybill_number = Column(String)
    passkey = Column(String)
    consumer_key = Column(String)
    consumer_secret = Column(String)


class SmsConfig(Base):
    __tablename__ = "sms_configs"

    id = Column(Integer, primary_key=True, index=True)
    gateway = Column(String, default="africas_talking")
    api_username = Column(String)
    api_key = Column(String)
    sender_id = Column(String)
    twilio_sid = Column(String, default="")
    twilio_token = Column(String, default="")
    twilio_from = Column(String, default="")
