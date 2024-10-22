from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .models import  User
from api.set_up.service import add_user_to_router, remove_user_from_router
from pydantic import BaseModel
from typing import List
from api.db.session import get_db,SessionLocal
from .schema import UserResponse,UserCreate

router = APIRouter()

@router.post("/users/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(username=user.username, email=user.email, hashed_password=user.password)  # In a real app, hash the password
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    add_user_to_router(user.username, user.password, "1M/1M")  # Default rate limit
    
    return new_user

@router.get("/users/", response_model=List[UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    remove_user_from_router(user.username)
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}