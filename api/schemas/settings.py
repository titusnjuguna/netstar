from pydantic import BaseModel


class MpesaConfig(BaseModel):
    environment: str
    paybillNumber: str
    passkey: str
    consumerKey: str
    consumerSecret: str


class MpesaConfigResponse(BaseModel):
    message: str
    config: MpesaConfig


class SmsConfig(BaseModel):
    gateway: str
    apiUsername: str
    apiKey: str
    senderId: str
    twilioSid: str = ""
    twilioToken: str = ""
    twilioFrom: str = ""


class SmsConfigResponse(BaseModel):
    message: str
    config: SmsConfig
