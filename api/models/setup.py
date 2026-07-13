from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base


class RouterInfo(Base):
    __tablename__ = "routers"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String)
    ip_address = Column(String,unique=True,index=True)
    tunnel_ip = Column(String,unique=True,nullable=True)
    password = Column(String)
    user_name = Column(String)
    location = Column(String)
    port = Column(Integer, default=8728)
    hotspot_name = Column(String)
    till_number = Column(String)
    phone_number = Column(String, nullable=True,default='254708520548')
    hostname = Column(String)
    reg_token = Column(String, unique=True, nullable=True)
    public_ip = Column(String, nullable=True)  
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=True)
    client = relationship("Clients", back_populates="routers")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)  


class Products(Base):
    __tablename__= "products"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String)
    price = Column(Integer)
    duration = Column(Integer)
    speed_limit = Column(String)
    data_limit = Column(String, default="Unlimited")
    router_id = Column(Integer, ForeignKey('routers.id'))
    router = relationship("RouterInfo", backref="products")
    subscription_id = Column(Integer,ForeignKey('subscriptions.id'),nullable=True)
    subscriptions = relationship("Subscription",backref="products")

    created_at = Column(DateTime, default=datetime.utcnow)
