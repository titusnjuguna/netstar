from typing import Union
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI,Request
import os
from fastapi.middleware.cors import CORSMiddleware
from api.db.session import engine, Base
from api.routers.payment import router as payment_router
from api.routers.setup import router as set_up_router
from api.routers.users import router as users_router
from api.routers.dashboard import router as dashboard_router
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declarative_base

template = Jinja2Templates(directory=os.path.join("api", "templates"))


app = FastAPI()

async def connect_to_db():
    conn = await asyncpg.connect(
        database="netstat",  # Replace with your actual database name
        user="postgres",
        password="208251001Tito",
        host="localhost",
        port=5432
    )
    return conn

@app.get("/test")
async def root():
    async with await connect_to_db() as conn:
        # Perform database operations here
        result = await conn.fetchval("SELECT 1")
        return {"message": "Connected to database!", "result": result}

# Initialize database on startup
@app.on_event("startup")
def startup():
    print(1234567)
    # await init_db()

   
# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*","http://localhost:5173/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(payment_router)
app.include_router(set_up_router)
app.include_router(users_router)
app.include_router(dashboard_router)