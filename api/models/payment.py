# database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base
from api.models.setup import *

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True) # index=True)
    device_identity = Column(String)  
    phone = Column(String) 
    product_id = Column(Integer, ForeignKey("products.id"))
    start_date = Column(DateTime,default=datetime.utcnow)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    payment_id = Column(Integer, ForeignKey("hotspot_payments.id"), nullable=True)
    product = relationship("Products", backref="subscriptions")
    payment =  relationship("HotspotPayments",backref="subscriptions")
    created_at = Column(DateTime, default=datetime.utcnow)

class PaymentDisbursement(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.utcnow)
    phone = Column(String)
    transaction_ref = Column(String)
    conversation_id = Column(String)
    success = Column(Boolean, default=False)
    user = relationship("User",backref="payments")
   

class HotspotPayments(Base):
    __tablename__ = "hotspot_payments"
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.utcnow)
    phone = Column(String)
    transaction_ref = Column(String)
    product_id = Column(Integer, ForeignKey("products.id"))
    CheckoutRequestID = Column(String)
    has_been_transferred = Column(Boolean, default=False)
    client_id = Column(Integer, ForeignKey("clients.id"))
    client = relationship("Clients",backref="hotspot_payments")
    products = relationship("Products",backref="hotspot_payments")
    subscriptions = relationship("Subscription", backref="hotspot_payments")
    created_at = Column(DateTime, default=datetime.utcnow)

class PaymentConfig(Base):
    __tablename__ = 'payment_configs'
    id = Column(Integer, primary_key=True, index=True)
    user = Column(String)
    password = Column(String)
    consumer_key = Column(String)
    consumer_secret= Column(String)
    initiator_name = Column(String)
    initiator_password = Column(String)
    merchant = Column(Integer)
    router_id = Column(Integer, ForeignKey('routers.id'))
 