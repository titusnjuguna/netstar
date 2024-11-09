from typing import Union
# from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI,Request
import os
from fastapi.middleware.cors import CORSMiddleware
from api.db.session import engine, Base
from api.payment.routes import router as payment_router
from api.set_up.routes import router as set_up_router
from api.users.routes import router as users_router
template = Jinja2Templates(directory=os.path.join("api", "templates"))
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
# from api.db.session import init_db
from sqlalchemy.ext.declarative import declarative_base

app = FastAPI()
import asyncpg
from fastapi import FastAPI

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

    print(123)
    # await init_db()

@app.get("/home", response_class=HTMLResponse)
async def home_page(request: Request):
    return template.TemplateResponse(
        request=request, name="index.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return template.TemplateResponse(
        request=request, name="dashboard.html")
    
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