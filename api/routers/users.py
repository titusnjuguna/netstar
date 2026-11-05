import random
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from api.models.users import  User
from api.services.setup import add_user_to_router, remove_user_from_router
from api.services.auth import verify_token, SECRET_KEY, ALGORITHM, hash_password
from typing import List
from api.db.session import get_db,SessionLocal
from api.schemas.users import *
from datetime import datetime, timedelta, timezone
import jwt
from api.services.admin import send_otp_email

router = APIRouter(
    prefix="/api", 
    tags=["Users"]
)

@router.post("/user/create", response_model=UserResponse)
@router.post("/v1/user/create", response_model=UserResponse)
@router.post("/create/user", response_model=UserResponse)
@router.post("/v1/create/user", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    db_email = db.query(User).filter(User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    client_id = user.client_id if user.client_id is not None else user.client
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        is_superuser=user.is_superuser if user.is_superuser is not None else False,
        is_active=user.is_active if user.is_active is not None else True,
        client_id=client_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # add_user_to_router(user.username, user.password, "1M/1M")  # Default rate limit
    
    return new_user

@router.get("/get/users", response_model=List[UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.get("/v1/get/client/users/{client_id}",response_model=List[UserResponse])
def get_client_users(client_id:int,skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: dict = Depends(verify_token)):
    users = db.query(User).filter(User.client_id==client_id).offset(skip).limit(limit).all()
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

    db_email = db.query(User).filter(User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    client_id = user.client_id if user.client_id is not None else user.client
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        is_superuser=user.is_superuser if user.is_superuser is not None else False,
        is_active=user.is_active if user.is_active is not None else True,
        client_id=client_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/v1/auth/create-superuser", response_model=UserResponse)
def create_superuser(user: UserCreate, db: Session = Depends(get_db)):
    db_email = db.query(User).filter(User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    client_id = user.client_id if user.client_id is not None else user.client
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        is_superuser=True,
        is_active=user.is_active if user.is_active is not None else True,
        client_id=client_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/v1/auth/login")
def login(user: UserLogin,background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(
        User.username == user.username
    ).first()
    if not db_user or (db_user.hashed_password != user.password and db_user.hashed_password != hash_password(user.password)):
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
    #generate random OTP and save to user
    otp = str(random.randint(100000, 999999))
    db_user.otp = otp
    #check if otp has expired first
    otp_expiration = db_user.otp_expiration
    if otp_expiration is None:
        is_expired = True
    else:
        if otp_expiration.tzinfo is None:
            otp_expiration = otp_expiration.replace(tzinfo=timezone.utc)
        is_expired = otp_expiration < datetime.now(timezone.utc)
    if is_expired:
        otp_expiration = datetime.now(timezone.utc) + timedelta(minutes=1440)
        #send otp in the background tasks
        background_tasks.add_task(send_otp_email, db_user.email,otp)
        db_user.otp_expiration = otp_expiration
        db.commit()
        db.refresh(db_user)
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
            "client": db_user.client_id
        }
    }


@router.post("/v1/auth/verify-otp")
def verify_otp(otp: OTPVerify, db: Session = Depends(get_db),_: dict = Depends(verify_token)):
    db_user = db.query(User).filter(
        User.email == otp.email
    ).first()
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    if db_user.otp != otp.otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP"
        )
    db_user.is_active = True
    db.commit()
    token = generate_token(db_user)
    return {"message": "OTP verified successfully", 
            "access_token": token, 
            "token_type": "bearer",
            "user": {
                "id": db_user.id,
                "email": db_user.email,
                "username": db_user.username,
                "is_superuser": db_user.is_superuser,
                "is_active": db_user.is_active,
                "client": db_user.client_id
            }
    }
