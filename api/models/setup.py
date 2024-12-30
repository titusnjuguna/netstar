from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base


class RouterInfo(Base):
    __tablename__ = "routers"
    id = Column(Integer,primary_key=True,index=True)
    ip_address = Column(String,unique=True,index=True)
    password = Column(String)
    user_name = Column(String)
    location = Column(String)
    port = Column(String)
    products = relationship("Products", back_populates="router")
    created_at = Column(DateTime,default=datetime.utcnow)

class Products(Base):
    __tablename__= "products"
    id = Column(Integer,primary_key=True,index=True)
    product_name = Column(String)
    product_category = Column(String)
    download = Column(Integer)
    upload = Column(Integer)
    price = Column(Integer)
    billing_period = Column(String)
    product_status = Column(String)
    router_id = Column(Integer, ForeignKey('routers.id'))
    router = relationship("RouterInfo", back_populates="products")
    created_at = Column(DateTime, default=datetime.utcnow)
