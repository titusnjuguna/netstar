# router_config.py
from routeros_api import RouterOsApiPool
from api.schemas.setup import RouterCreate
from api.db.session import get_db
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from api.models.setup import RouterInfo
import logging
from sqlalchemy.exc import IntegrityError
from routeros_api import RouterOsApiPool, exceptions
from librouteros import connect
logger = logging.getLogger(__name__)



def check_mikrotik_status(host,username,password,port):
    try:
        # Connect to the MikroTik API
        connection = RouterOsApiPool(host, username=username, password=password, port=port)
        api = connection.get_api()

        # Perform a simple command to test connectivity (e.g., fetch system resource details)
        response = api.get_resource('/system/resource').get()
        if response:
            print("Router is online!")
            for data in response:
                print(f"Uptime: {data.get('uptime')}")
                print(f"CPU Load: {data.get('cpu-load')}%")
        else:
            print("Router is unreachable or returned no data.")

        # Disconnect
        connection.disconnect()

    except exceptions.RouterOsApiConnectionError:
        print("Failed to connect. Router is offline or inaccessible.")
    except exceptions.RouterOsApiCommunicationError as e:
        print(f"Communication error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


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

def set_speed_limit(download_speed: int, upload_speed: int,router_id:int,db:any):
    router = db.query(RouterInfo).filter(RouterInfo.id == router_id).first()
    username = router.user_name
    password = router.password
    ip_address = router.ip_address

    download_speed_kbps = download_speed * 1024
    upload_speed_kbps = upload_speed * 1024
    try:
        connection = connect(username=username, password=password,host=ip_address)
        connection('/queue/simple/add', 
               name=f"Limit_{username}",
               target=f"{username}",  # You can use IP address or username depending on the router config
               maxlimit=f"{download_speed_kbps}k/{upload_speed_kbps}k",
               priority=8)
    except Exception as e:
        return f'error occured {e}'