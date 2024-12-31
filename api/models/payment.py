# database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db import Base


# class User(Base):
#     __tablename__ = "users"
#     id = Column(Integer, primary_key=True, index=True)
#     username = Column(String, unique=True, index=True)
#     hashed_password = Column(String)
#     email = Column(String, unique=True, index=True)
#     is_active = Column(Boolean, default=True)
#     created_at = Column(DateTime, default=datetime.utcnow)
#     subscriptions = relationship("Subscription", back_populates="user")

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
    start_date = Column(DateTime, default=datetime.utcnow)
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
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"))

    user = relationship("User")
    subscription = relationship("Subscription")

class Transactions(Base):
    id = Column(Integer,primary_key=True,index=True)
    phone =
    transaction_ref =
    expiry_date = 
    amount = 

