from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Union, List
from sqlalchemy.ext.asyncio import AsyncSession
from api.db.session import get_db
from . import service

router = APIRouter()

@router.get("/payments")
def get_payments():
    pass


