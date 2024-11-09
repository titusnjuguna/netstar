# from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import Session
# from sqlalchemy.orm import sessionmaker
# from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine

# SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://postgres:208251001#Tito@localhost:5432/netstar"
# engine = create_async_engine(SQLALCHEMY_DATABASE_URL,echo=True)
# # SessionLocal = sessionmaker(bind=engine,class_=AsyncSession,expire_on_commit=False,autocommit=False,autoflush=False)

# Base = declarative_base()
# # Base.metadata.create_all(engine)

# # def get_db():
# #     db = SessionLocal()
# #     try:
# #         yield db
# #     finally:
# #         db.close()
# SessionLocal = sessionmaker(
#     engine, expire_on_commit=False, class_=AsyncSession
# )

# async def get_db():
#     async with SessionLocal() as session:
#         yield session

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime,MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from contextlib import asynccontextmanager

# Database URL
# SQLALCHEMY_DATABASE_URL = "postgresql+asyncpg://postgres:208251001Tito@localhost:5432/postgres"
# SQLALCHEMY_DATABASE_URL = wifi_billing.db

metadata = MetaData()
# # Create async engine
# engine = create_async_engine(SQLALCHEMY_DATABASE_URL,
#     echo=True,  # Set to False in production
#     pool_pre_ping=True,  # Enable connection health checks
#     pool_size=5,  # Adjust based on your needs
#     max_overflow=10  # Adjust based on your needs
# )

# # Create declarative base
# Base = declarative_base()


# # async with engine.begin() as conn:
# #     await conn.run_sync(Base.metadata.create_all)

# # Create async session factory
# SessionLocal = sessionmaker(
#     engine,
#     class_=AsyncSession,
#     expire_on_commit=False,
#     autocommit=False,
#     autoflush=False
# )

# Database dependency
# @asynccontextmanager
# async def get_db():
#     async with SessionLocal() as session:
#         try:
#             yield session
#             await session.commit()
#         except Exception:
#             await session.rollback()
#             raise
#         finally:
#             await session.close()
# @asynccontextmanager
# async def get_db():
#     async with SessionLocal() as session:
#         try:
#             yield session
#         except Exception:
#             await session.rollback()
#             raise

# @asynccontextmanager
# async def get_db():
#     async with async_session() as session:  # assuming async_session() is configured with your database

#         yield session
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


from sqlalchemy.orm import Session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base = declarative_base()

