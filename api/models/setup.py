from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base


class RouterInfo(Base):
    __tablename__ = "routers"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String)
    ip_address = Column(String,unique=True,index=True)
    password = Column(String)
    user_name = Column(String)
    location = Column(String)
    port = Column(Integer, default=8728)
    hotspot_name = Column(String)
    till_number = Column(String)
    created_at = Column(DateTime,default=datetime.utcnow)

class Products(Base):
    __tablename__= "products"
    id = Column(Integer,primary_key=True,index=True)
    name = Column(String)
    price = Column(Integer)
    duration = Column(Integer)  # validity period in hours
    speed_limit = Column(String)
    data_limit = Column(String, default="Unlimited")
    created_at = Column(DateTime, default=datetime.utcnow)
