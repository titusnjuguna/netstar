from api.models.admin import Clients,ClientBilling
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class ClientCreateRequest(BaseModel):
    name: str
    email: str
    phone_number: str
     


class ClientResponse(BaseModel):
    id: int
    name: str
    email: str
    phone_number: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class ClientBillingRequest(BaseModel):
    client_id: int
    description: str
    amount: int
    due_date: datetime
    total_due: Optional[int] = 0
    balance_brought_forward: Optional[int] = 0
    has_paid: Optional[bool] = False


class ClientBillingResponse(BaseModel):
    id: int
    client_id: int
    description: str
    amount: int
    due_date: datetime
    total_due: int
    status: str  # e.g., unpaid, paid, overdue
    balance_brought_forward: int
    has_paid: bool
    created_at: datetime
    updated_at: datetime