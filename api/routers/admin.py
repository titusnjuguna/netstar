from api.models.admin import Clients, ClientBilling
from api.models.setup import RouterInfo
from api.services.auth import verify_token
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from api.schemas.admin import *
from api.schemas.setup import RouterOut
from fastapi import APIRouter, Depends
from api.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"])

@router.post("/create-client", response_model=ClientResponse)
def create_client(client: ClientCreateRequest, db: Session = Depends(get_db)):#, _: dict = Depends(verify_token)):
    db_client = Clients(
        name=client.name,
        email=client.email,
        phone_number=client.phone_number,
        is_active=True
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@router.get("/clients", response_model=List[ClientResponse])
def get_clients(db: Session = Depends(get_db)):#, _: dict = Depends(verify_token)):
    clients = db.query(Clients).all()
    return [
        ClientResponse(
            id=c.id,
            name=c.name,
            email=c.email,
            phone_number=c.phone_number,
            is_active=c.is_active,
            created_at=c.created_at,
            updated_at=c.updated_at
        )
        for c in clients
    ]

@router.post("/create-billing", response_model=ClientBillingResponse)
def create_billing(billing: ClientBillingResponse, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    db_billing = ClientBilling(
        client_id=billing.client_id,
        description=billing.description,
        amount=billing.amount,
        due_date=billing.due_date,
        total_due=billing.total_due,
        status=billing.status,
        balance_brought_forward=billing.balance_brought_forward,
        has_paid=billing.has_paid
    )
    db.add(db_billing)
    db.commit()
    db.refresh(db_billing)
    return db_billing



@router.get("/billings", response_model=List[ClientBillingResponse])
def get_billings(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    billings = db.query(ClientBilling).all()
    return [
        ClientBillingResponse(
            id=b.id,
            client_id=b.client_id,
            description=b.description,
            amount=b.amount,
            due_date=b.due_date,
            total_due=b.total_due,
            status=b.status,
            balance_brought_forward=b.balance_brought_forward,
            has_paid=b.has_paid,
            created_at=b.created_at,
            updated_at=b.updated_at
        )
        for b in billings
    ]



@router.get("/all-routers", response_model=List[RouterOut])
def get_all_routers(db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    routers = db.query(RouterInfo).all()
    return [
        RouterInfo(
            id=r.id,
            name=r.name,
            email=r.email,
            phone_number=r.phone_number,
            billing_address=r.billing_address,
            billing_email=r.billing_email,
            billing_phone=r.billing_phone,
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in routers
    ]   
