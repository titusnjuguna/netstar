
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_superuser: Optional[bool] = False
    is_active: Optional[bool] = True
    client: Optional[int] = None
    client_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: Optional[bool] = False
    client_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class MPayRequest(BaseModel):
    routerId : str
    reference : str

class VoucherRequest(BaseModel):
    voucher: str
    routerId : int

class PayRequest(BaseModel):
    phone: str
    productId: Optional[str] = None
    amount: Optional[float] = None
    client_id: Optional[int] = None
    clientId: Optional[int] = None

class ClientWithdrawRequest(BaseModel):
    amount: float
    client_id: Optional[int] = None
    clientId: Optional[int] = None
    phone: Optional[str] = None
    otp: Optional[str] = None

class WithdrawOtpRequest(BaseModel):
    amount: float
    client_id: Optional[int] = None
    clientId: Optional[int] = None

class AccountDetailsResponse(BaseModel):
    message: str = "Account details retrieved successfully"
    success: bool = True
    code: int = 200
    currency: str = "KES"
    balance: float = 0.0
    pendingBalance: float = 0.0
    pending_balance: float = 0.0
    available_balance: float = 0.0
    total_revenue: float = 0.0
    total_withdrawn: float = 0.0
    total_routers: int = 0
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PayResponse(BaseModel):
    pass
    
class PaymentConfigRequest(BaseModel):
    user : str
    password : str
    consumer_key : str
    consumer_secret : str
    initiator_name: str
    initiator_password : str
    merchant : int
    router_id : int

class PaymentConfigResponse(BaseModel):
    message:str
    success: bool
    code: int

class GeneralResponse(BaseModel):
    message: str
    success: bool
    code: int
    payment_ref: Optional[str] = None
    hotspot_username: Optional[str] = None
    hotspot_password: Optional[str] = None
    login_url: Optional[str] = None
    otp_required: Optional[bool] = None
    phone: Optional[str] = None


class SubscriptionOut(BaseModel):
    id: str
    mac: str
    phone: str
    productName: str
    startTime: datetime
    expiryTime: Optional[datetime] = None
    dataUsed: int
    dataCap: int
    status: str
    ipAddress: str


class PaginationInfo(BaseModel):
    page: int
    perPage: int
    totalItems: int
    totalPages: int


class SubscriptionsListResponse(BaseModel):
    message: str
    subscriptions: List[SubscriptionOut]
    pagination: PaginationInfo


class GenerateVoucherRequest(BaseModel):
    product_id: int
    phone: str

class GetVouchersResponse(BaseModel):
    id: int
    voucher_code: str
    phone: str
    generated_date: datetime
    status: str
    product_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class GetVouchersGeneralResponse(BaseModel):
    message: str
    success: bool
    code: int
    vouchers: List[GetVouchersResponse]

class TransactionItem(BaseModel):
    id: str
    date: datetime
    type: str  # 'credit' | 'debit'
    description: str
    routerId: Optional[str] = None
    routerName: Optional[str] = None
    amount: float
    balanceAfter: float
    status: str  # 'completed' | 'pending' | 'failed'

    model_config = ConfigDict(from_attributes=True)

class WalletTransactionsResponse(BaseModel):
    message: str = "Transactions retrieved successfully"
    success: bool = True
    code: int = 200
    transactions: List[TransactionItem] = []
    pagination: PaginationInfo