from datetime import datetime
from symtable import Class
from api.db.session import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship



class Clients(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    phone_number = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    routers = relationship("RouterInfo", back_populates="client")



class ClientBilling(Base):
    __tablename__ = "client_billing"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Integer, nullable=False)
    due_date = Column(DateTime, nullable=False)
    total_due = Column(Integer, default=0)
    status = Column(String(50), default="unpaid")  # e.g., unpaid, paid, overdue
    balance_brought_forward = Column(Integer, default=0)
    has_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
