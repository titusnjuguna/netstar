from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime,Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from api.db.session import Base


class RouterInfo(Base):
    __tablename__ = "Routers"
    id = Column(Integer,primary_key=True,index=True)
    ip_address = Column(String,unique=True,index=True)
    password = Column(String)
    user_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
