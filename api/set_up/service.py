# router_config.py
from routeros_api import RouterOsApiPool
from .schema import RouterCreate
from api.db.session import get_db
from sqlalchemy.orm import Session
from fastapi import Depends
from .models import RouterInfo
import logging
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)
# ROUTER_IP = "192.168.88.1"
# ROUTER_USERNAME = "admin"
# ROUTER_PASSWORD = "password"


def add_router_info(router:RouterCreate,db:Session = Depends(get_db)):
    try:
        new_class = RouterInfo()
        db.add(new_class)
        db.commit()
        db.refresh(new_class)
        return True
    except IntegrityError:
        db.rollback()
        return False
    

def get_router_connection(ROUTER_IP,ROUTER_USERNAME,ROUTER_PASSWORD):
    connection = RouterOsApiPool(
        host=ROUTER_IP,
        username=ROUTER_USERNAME,
        password=ROUTER_PASSWORD,
        plaintext_login=True
    )
    return connection.get_api()

def add_user_to_router(username, password, rate_limit):
    api = get_router_connection()
    api.get_resource('/ip/hotspot/user').add(
        name=username,
        password=password,
        profile="default"
    )
    api.get_resource('/queue/simple').add(
        name=username,
        target=f"<{username}>",
        max_limit=rate_limit
    )

def remove_user_from_router(username):
    api = get_router_connection()
    api.get_resource('/ip/hotspot/user').remove(name=username)
    api.get_resource('/queue/simple').remove(name=username)

def update_user_rate_limit(username, new_rate_limit):
    api = get_router_connection()
    api.get_resource('/queue/simple').set(
        name=username,
        max_limit=new_rate_limit
    )