import random
import string
from api.models.admin import Clients, ClientBilling
from api.models.setup import RouterInfo
from api.models.users import User
from api.services.auth import hash_password, verify_token
from api.services.sms import send_email
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from api.schemas.admin import *
from api.schemas.setup import RouterOut
from fastapi import APIRouter, Depends,BackgroundTasks, HTTPException
from api.db.session import get_db
from sqlalchemy.orm import Session
from api.services.auth import hash_password

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"])

@router.post("/create-client", response_model=ClientResponse)
def create_client(client: ClientCreateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):#, _: dict = Depends(verify_token)):
    db_client = Clients(
        name=client.name,
        email=client.email,
        phone_number=client.phone_number,
        is_active=True
    )
    db.add(db_client)
    db.commit()
    #create a user superadmin for the client with default password
    generate_alphanumeric = lambda length: ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    default_password = generate_alphanumeric(7)
    message = f"Hello {client.name}, your account has been created. Your default password is: {default_password}. Please change it after logging in."
    new_user = User(
        username=client.email,
        email=client.email,
        hashed_password=hash_password(default_password),  # In a real app, hash the password
        is_superadmin=True,
        client_id=db_client.id
    )
    db.add(new_user)
    db.commit()
    background_tasks.add_task(send_email, db_client.email, message)
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
