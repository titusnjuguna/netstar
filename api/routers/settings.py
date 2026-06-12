from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.db.session import get_db
from api.models.settings import MpesaConfig as MpesaConfigModel, SmsConfig as SmsConfigModel
from api.schemas.settings import (
    MpesaConfig,
    MpesaConfigResponse,
    SmsConfig,
    SmsConfigResponse,
)
from api.services.auth import verify_token

router = APIRouter(
    prefix="/api",
    tags=["Settings"]
)


def _mpesa_to_schema(config: MpesaConfigModel) -> MpesaConfig:
    return MpesaConfig(
        environment=config.environment,
        paybillNumber=config.paybill_number,
        passkey=config.passkey,
        consumerKey=config.consumer_key,
        consumerSecret=config.consumer_secret,
    )


def _sms_to_schema(config: SmsConfigModel) -> SmsConfig:
    return SmsConfig(
        gateway=config.gateway,
        apiUsername=config.api_username,
        apiKey=config.api_key,
        senderId=config.sender_id,
        twilioSid=config.twilio_sid,
        twilioToken=config.twilio_token,
        twilioFrom=config.twilio_from,
    )


@router.get("/v1/get/mpesa-config", response_model=MpesaConfigResponse)
def get_mpesa_config(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    config = db.query(MpesaConfigModel).first()
    if not config:
        config = MpesaConfigModel(
            environment="sandbox", paybill_number="", passkey="",
            consumer_key="", consumer_secret="",
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return MpesaConfigResponse(message="Mpesa config fetched successfully", config=_mpesa_to_schema(config))


@router.put("/v1/update/mpesa-config", response_model=MpesaConfigResponse)
def update_mpesa_config(payload: MpesaConfig, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    config = db.query(MpesaConfigModel).first()
    if not config:
        config = MpesaConfigModel()
        db.add(config)

    config.environment = payload.environment
    config.paybill_number = payload.paybillNumber
    config.passkey = payload.passkey
    config.consumer_key = payload.consumerKey
    config.consumer_secret = payload.consumerSecret

    db.commit()
    db.refresh(config)

    return MpesaConfigResponse(message="Mpesa config updated successfully", config=_mpesa_to_schema(config))


@router.get("/v1/get/sms-config", response_model=SmsConfigResponse)
def get_sms_config(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    config = db.query(SmsConfigModel).first()
    if not config:
        config = SmsConfigModel(
            gateway="africas_talking", api_username="", api_key="", sender_id="",
            twilio_sid="", twilio_token="", twilio_from="",
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return SmsConfigResponse(message="SMS config fetched successfully", config=_sms_to_schema(config))


@router.put("/v1/update/sms-config", response_model=SmsConfigResponse)
def update_sms_config(payload: SmsConfig, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    config = db.query(SmsConfigModel).first()
    if not config:
        config = SmsConfigModel()
        db.add(config)

    config.gateway = payload.gateway
    config.api_username = payload.apiUsername
    config.api_key = payload.apiKey
    config.sender_id = payload.senderId
    config.twilio_sid = payload.twilioSid
    config.twilio_token = payload.twilioToken
    config.twilio_from = payload.twilioFrom

    db.commit()
    db.refresh(config)

    return SmsConfigResponse(message="SMS config updated successfully", config=_sms_to_schema(config))
