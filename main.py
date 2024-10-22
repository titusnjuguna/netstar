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

app = FastAPI(title="WiFi Billing System")

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
    allow_origins=["*"],
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