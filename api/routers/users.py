from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.models.users import  User
from api.services.setup import add_user_to_router, remove_user_from_router
from api.services.auth import verify_token, SECRET_KEY, ALGORITHM
from pydantic import BaseModel
from typing import List
from api.db.session import get_db,SessionLocal
from api.schemas.users import UserResponse,UserCreate

router = APIRouter(
    prefix="/api", 
    tags=["Users"]
)

@router.post("/user/create", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(username=user.username, email=user.email, hashed_password=user.password)  # In a real app, hash the password
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # add_user_to_router(user.username, user.password, "1M/1M")  # Default rate limit
    
    return new_user

@router.get("/get/users", response_model=List[UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.delete("/delete/user/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    remove_user_from_router(user.username)
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

from datetime import datetime, timedelta, timezone
import jwt

def generate_token(user: User):
    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12)
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/v1/auth/register-user", response_model=UserResponse)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    new_user = User(username=user.username, email=user.email, hashed_password=user.password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/v1/auth/create-superuser", response_model=UserResponse )
def create_superuser(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(username=user.username, email=user.email, hashed_password=user.password, is_superuser=True)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/v1/auth/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(
        User.username == user.username
    ).first()
    print (db_user)

    if not db_user or db_user.hashed_password != user.password:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )
    if not db_user.is_active:
        return {
            "status_code":403,
            "access_token": None,
            "token_type": "bearer",
            "user": {}}
    token = generate_token(db_user)
    return {
        "status_code":200,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "email": db_user.email,
            "username": db_user.username,
            "is_superuser": db_user.is_superuser,
            "is_active": db_user.is_active,
            "client": db_user.client
        }
    }