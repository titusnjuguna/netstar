# database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base
from api.models.setup import RouterInfo

class Package(Base):
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    price = Column(Float)
    data_limit = Column(Integer)  # in MB
    speed = Column(Integer)  # in Mbps

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    package_id = Column(Integer, ForeignKey("packages.id"))
    start_date = Column(DateTime,default=datetime.utcnow)
    end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    # user = relationship("User", back_populates="subscriptions")
    package = relationship("Package")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    payment_date = Column(DateTime, default=datetime.utcnow)
    phone = Column(String)
    transaction_ref = Column(String)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"))
    user = relationship("User")
    subscription = relationship("Subscription")

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
    # router = relationship("RouterInfo", back_populates="products")