from dotenv import load_dotenv
load_dotenv()

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
from api.routers.settings import router as settings_router
from api.routers.admin import router as admin_router
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declarative_base

template = Jinja2Templates(directory=os.path.join("api", "templates"))
#test fixing

app = FastAPI()

async def connect_to_db():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"].replace("+psycopg2", ""))
    return conn

@app.get("/test")
async def root():
    conn = await connect_to_db()
    try:
        result = await conn.fetchval("SELECT 1")
        return {"message": "Connected to database!", "result": result}
    finally:
        await conn.close()

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
Base.metadata.create_all(bind=engine,checkfirst=True)

# Include routers
app.include_router(payment_router)
app.include_router(set_up_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(admin_router)