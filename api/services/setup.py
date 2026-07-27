import os
import re
import uuid
import socket
import select
import struct
import time
import ftplib
import string
import secrets
import logging
import concurrent.futures
from io import BytesIO
import subprocess
from api.schemas.setup import *
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from api.models.setup import RouterInfo
from fastapi import  HTTPException
from routeros_api import RouterOsApiPool, exceptions
from librouteros import connect
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
from sqlalchemy import  select

load_dotenv()

logger = logging.getLogger(__name__)
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_template_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates"))
)
class _Settings:
    WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")
    HUB_PUBLIC_KEY = os.environ.get("HUB_PUBLIC_KEY", "")
    HUB_TUNNEL_IP = os.getenv("HUB_TUNNEL_IP","")
    HUB_ENDPOINT_HOST = os.environ.get("HUB_ENDPOINT_HOST", "")
    HUB_ENDPOINT_PORT = int(os.environ.get("HUB_ENDPOINT_PORT", "51820"))
    CALLBACK_BASE_URL = os.environ.get("CALLBACK_BASE_URL", API_BASE_URL)
    TUNNEL_POOL_FIRST_HOST_OCTET = int(os.environ.get("TUNNEL_POOL_FIRST_HOST_OCTET", "2"))
    TUNNEL_POOL_LAST_HOST_OCTET = int(os.environ.get("TUNNEL_POOL_LAST_HOST_OCTET", "254"))
    Backend_BASE_URL = os.environ.get("BACKEND_BASE_URL","https://api.net.babybull.cc/api/v1/")

settings = _Settings()

class MikrotikOperation:
    def __init__(self,router:RouterInfo,**kwargs):
        self.router = router
        self.host = router.tunnel_ip or router.ip_address
        self.username = router.user_name
        self.password = router.password
        self.port = kwargs.get("port", 8728)
        self.connection = None
        self.api = None
        self.product = kwargs.get("product")
        self.host_name = router.hostname
        self.phone = kwargs.get("phone")
        self.uptime =  kwargs.get("uptime")
        self.hotspot_password = kwargs.get("hotspot_password")

    def __initiate_connection(self):
        try:
            self.connection = RouterOsApiPool(
                host=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                plaintext_login=True
            )
            self.connection.set_timeout(5)
            self.api = self.connection.get_api()
        except exceptions.RouterOsApiConnectionError:
            raise HTTPException(status_code=503, detail="Router is offline or inaccessible.")
        except exceptions.RouterOsApiCommunicationError as e:
            raise HTTPException(status_code=500, detail=f"Communication error: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
        
    def _parse_speed_mbps(self):
    
        speed_limit = self.product.speed_limit if self.product else None
        if not speed_limit or speed_limit.lower() == 'unlimited':
            return None
        m = re.search(r'(\d+(?:\.\d+)?)',speed_limit)
        if not m:
            return None
        num = m.group(1).rstrip('.')
        return f"{num}M/{num}M"
        
    def create_router_profile_product(self):
        if not self.api:
            self.__initiate_connection()
        profile_name = self.product.name
        speed = self._parse_speed_mbps() or "2M/2M"
        try:
            self.api.get_resource('/ip/hotspot/user/profile').add(**{
                'name': profile_name,
                'rate-limit': speed,
                'shared-users': '1',
            })
            logger.info("Created hotspot profile '%s' (%s) on %s", profile_name, speed, self.host)
        except Exception as e:
            err = str(e).lower()
            if 'already have' in err or 'already exists' in err or 'failure' in err:
                logger.info("Profile '%s' already exists on %s", profile_name, self.host)
            else:
                logger.warning("Failed to create profile '%s' on %s: %s", profile_name, self.host, e)

    def check_mikrotik_status(self):
        try:
            self.__initiate_connection()
            response = self.api.get_resource('/system/resource').get()
            if response:
                print("Router is online!")
                for data in response:
                    print(f"Uptime: {data.get('uptime')}")
                    print(f"CPU Load: {data.get('cpu-load')}%")
            else:
                print("Router is unreachable or returned no data.")
            self.connection.disconnect()
        except exceptions.RouterOsApiConnectionError:
            print("Failed to connect. Router is offline or inaccessible.")
        except exceptions.RouterOsApiCommunicationError as e:
            print(f"Communication error: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")


    def format_uptime(uptime_str):
        if not uptime_str:
            return "0d 0h 0m"
        weeks = days = hours = minutes = 0
        num = ""
        for ch in uptime_str:
            if ch.isdigit():
                num += ch
                continue
            value = int(num) if num else 0
            if ch == 'w':
                weeks = value
            elif ch == 'd':
                days = value
            elif ch == 'h':
                hours = value
            elif ch == 'm':
                minutes = value
            num = ""
        return f"{weeks * 7 + days}d {hours}h {minutes}m"


    def get_router_live_stats(self):
        try:
            self.__initiate_connection()
            api = self.api
            resource = list(api.get_resource('/system/resource').get())
            active = list(api.get_resource('/ip/hotspot/active').get())
            self.connection.disconnect()
            info = resource[0] if resource else {}
            total_memory = int(info.get('total-memory', 0) or 0)
            free_memory = int(info.get('free-memory', 0) or 0)
            memory_usage = round((total_memory - free_memory) / total_memory * 100) if total_memory else 0

            return {
                "status": "online",
                "cpuLoad": int(info.get('cpu-load', 0) or 0),
                "memoryUsage": memory_usage,
                "uptime": self.format_uptime(info.get('uptime', '')),
                "activeUsers": len(active),
                "error": None,
            }
        except Exception as e:
            logger.warning("Could not connect to MikroTik at %s:%s — %s", self.host, self.port, e)
            return {"status": "offline", "cpuLoad": 0, "memoryUsage": 0, "uptime": "0d 0h 0m", "activeUsers": 0, "error": str(e)}
    
    def get_available_user_profiles(self):
        self.__initiate_connection()
        profiles = list(self.api.get_resource('/ip/hotspot/user/profile').get())
        self.connection.disconnect()
        if not profiles:
            logger.warning(f"Could not fetch profiles from %s: %s",self.host, "No profiles found")
            return []
        return profiles
       
    
    def get_profile_by_name(self):
        profiles = self.get_available_user_profiles()
        return next((p for p in profiles if p.get('name') == self.product.name), None)

    def match_product_to_profile(self):
        return self.get_profile_by_name()

    def refresh_router_products(self):
        self.__initiate_connection()
        try:
            self.api.get_resource('/tool').call('fetch', arguments={
                'url': f"http://167.86.76.158:8070/api/v1/get/products?host={self.host_name}",
                'output': 'file',
                'dst-path': 'products.json',
            })
        except Exception as e:
            logger.warning("refresh_router_products skipped on %s: %s", self.host, e)
        finally:
            self.connection.disconnect()
        return True

    def fetch_hotspot_details(self):
        self.__initiate_connection()
        try:
            self.api.get_resource('/tool').call('fetch', arguments={
                'url': f"http://167.86.76.158:8070/api/v1/get/hotspot-details?host={self.host_name}",
                'output': 'file',
                'dst-path': 'more.json',
            })
        except Exception as e:
            logger.warning("fetch_hotspot_details skipped on %s: %s", self.host, e)
        finally:
            self.connection.disconnect()
        return True

    def get_active_session(self, phone: str) -> dict:
        """Return MAC, IP, and hostname for a currently-connected hotspot user."""
        self.__initiate_connection()
        try:
            active = list(self.api.get_resource('/ip/hotspot/active').get())
        finally:
            self.connection.disconnect()
        session = next((s for s in active if s.get('user') == phone), None)
        if not session:
            return {}
        return {
            'mac': session.get('mac-address', ''),
            'ip': session.get('address', ''),
            'hostname': session.get('host-name', ''),
            'uptime': session.get('uptime', ''),
        }

    def create_hotspot_user(self):
        self.__initiate_connection()
        users = self.api.get_resource('/ip/hotspot/user')
        limit_uptime = f"{self.uptime}m"
        profile_name = self.product.name
        

        def _add(profile_name):
            users.add(**{'name': self.phone, 'password': self.hotspot_password,
                        'limit-uptime': limit_uptime, 'profile': profile_name})

        def _update():
            all_users = list(users.get())
            existing = next((u for u in all_users if u.get('name') == self.phone), None)
            if not existing:
                raise RuntimeError(f"User '{self.phone}' not found for update on {self.host}")
            logger.info("Existing user dict for %s: %s", self.phone, existing)
            dot_id = existing.get('.id') or existing.get('id')
            if dot_id is None:
                dot_id = next((v for k, v in existing.items() if 'id' in k.lower()), None)
            if dot_id is None:
                raise RuntimeError(f"Cannot find .id for user '{self.phone}' — dict: {existing}")
            users.set(**{'.id': dot_id, 'password': self.hotspot_password,
                        'limit-uptime': limit_uptime, 'profile': profile_name})
            logger.info("Hotspot user updated: %s on %s", self.phone, self.host)
        try:
            _add(profile_name)
            logger.info("Hotspot user created: %s on %s", self.phone, self.host)
        except Exception as add_err:
            err_str = str(add_err).lower()
            if 'already have user' in err_str:
                _update()
            elif 'does not match any value of profile' in err_str:
                logger.warning("Profile '%s' not found on %s, falling back to default", profile_name, self.host)
                try:
                    _add('default')
                    logger.info("Hotspot user created with default profile: %s on %s", self.phone, self.host)
                except Exception as fallback_err:
                    if 'already have user' in str(fallback_err).lower():
                        _update()
                    else:
                        raise RuntimeError(f"Cannot create hotspot user '{self.phone}': {fallback_err}")
            else:
                raise RuntimeError(f"Cannot create hotspot user '{self.phone}': {add_err}")
        return self.phone, self.password


def render_captive_portal_html(hotspot_name, router_id, till_number, api_base_url=API_BASE_URL):
    template = _template_env.get_template("hotspot_login.html")
    return template.render(
        hotspot_name=hotspot_name,
        router_id=router_id,
        till_number=till_number,
        api_base_url=api_base_url,
    )


def deploy_captive_portal(host, username, password, html_content, port=21):
    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=10)
        ftp.login(username, password)
        try:
            ftp.cwd('hotspot')
        except ftplib.error_perm:
            ftp.mkd('hotspot')
            ftp.cwd('hotspot')
        ftp.storbinary('STOR login.html', BytesIO(html_content.encode('utf-8')))
        ftp.quit()
        return True, "Captive portal page deployed to /hotspot/login.html"
    except Exception as e:
        return False, f"Failed to deploy captive portal: {e}"


MNDP_PORT = 5678

# Well-known OUI prefixes registered to MikroTik / Routerboard.com
_MIKROTIK_OUI_PREFIXES = (
    "00:0C:42", "4C:5E:0C", "6C:3B:6B", "74:4D:28", "78:9A:18",
    "B8:69:F4", "CC:2D:E0", "D4:CA:6D", "E4:8D:8C", "DC:2C:6E", "2C:C8:1B",
)

_MNDP_TLV_NAMES = {
    0x0001: "mac",
    0x0005: "identity",
    0x0007: "version",
    0x0008: "platform",
    0x000C: "board",
}


def _read_local_routes():
    """
    Parse /proc/net/route and return (be_network, be_mask) for each
    directly connected (non-gateway) UP route. Values are big-endian integers
    suitable for use with socket.inet_ntoa / struct.pack('>I', ...).
    """
    routes = []
    try:
        with open('/proc/net/route') as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) < 8:
                    continue
                flags = int(parts[3], 16)
                if not (flags & 0x1) or (flags & 0x2):  # skip !UP and gateway routes
                    continue
                # /proc/net/route stores addresses as little-endian hex
                dest_le = int(parts[1], 16)
                mask_le = int(parts[7], 16)
                if mask_le == 0:
                    continue
                be_dest = struct.unpack('>I', struct.pack('<I', dest_le))[0]
                be_mask = struct.unpack('>I', struct.pack('<I', mask_le))[0]
                routes.append((be_dest & be_mask, be_mask))
    except OSError:
        pass
    return routes


def _get_local_broadcast_addresses():
    """Broadcast address for every directly connected subnet, plus the limited broadcast."""
    addresses = {'255.255.255.255'}
    for be_net, be_mask in _read_local_routes():
        be_bcast = be_net | (~be_mask & 0xFFFFFFFF)
        bcast = socket.inet_ntoa(struct.pack('>I', be_bcast))
        if bcast not in ('0.0.0.0', '255.255.255.255'):
            addresses.add(bcast)
    return addresses


def _get_local_subnet_hosts():
    """All host addresses in directly connected subnets (clamped to /24 max)."""
    hosts = []
    for be_net, be_mask in _read_local_routes():
        prefix = bin(be_mask).count('1')
        if prefix < 24:
            be_mask = 0xFFFFFF00
            be_net = be_net & be_mask
        host_count = (~be_mask) & 0xFFFFFFFF  # e.g. 255 for /24
        for i in range(1, host_count):
            hosts.append(socket.inet_ntoa(struct.pack('>I', be_net | i)))
    return hosts


def _check_mikrotik_port(ip, timeout=0.5):
    for port in (8728, 8291):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return {
                    "ipAddress": ip,
                    "mac": None,
                    "identity": None,
                    "platform": "MikroTik",
                    "board": None,
                    "version": None,
                    "method": "port-scan",
                }
        except OSError:
            continue
    return None


def discover_via_port_scan(timeout=5):
    """Parallel TCP scan of local subnets for MikroTik API (8728) or Winbox (8291)."""
    candidates = _get_local_subnet_hosts()
    if not candidates:
        return []
    found = {}
    per_host = max(0.3, min(1.0, timeout / 2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(64, len(candidates))) as ex:
        futures = {ex.submit(_check_mikrotik_port, ip, per_host): ip for ip in candidates}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                result = future.result()
                if result:
                    found[result['ipAddress']] = result
        except concurrent.futures.TimeoutError:
            pass
    return list(found.values())


def _parse_mndp_packet(data):
    info = {}
    pos = 4  # skip the 4-byte MNDP header
    while pos + 4 <= len(data):
        tlv_type = int.from_bytes(data[pos:pos + 2], "big")
        tlv_len = int.from_bytes(data[pos + 2:pos + 4], "big")
        pos += 4
        value = data[pos:pos + tlv_len]
        pos += tlv_len
        name = _MNDP_TLV_NAMES.get(tlv_type)
        if name == "mac" and len(value) == 6:
            info["mac"] = ":".join(f"{b:02X}" for b in value)
        elif name:
            info[name] = value.decode("utf-8", errors="ignore")
    return info


def discover_via_mndp(timeout=5):
    """Listen for MikroTik Neighbor Discovery Protocol broadcasts on the local network."""
    devices = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print(f"Listening for MNDP broadcasts on UDP port {MNDP_PORT} for {timeout} seconds...")
    try:
        sock.bind(("", MNDP_PORT))
    except OSError as e:
        logger.warning("MNDP: could not bind port %d: %s", MNDP_PORT, e)
        sock.close()
        return []

    for bcast in _get_local_broadcast_addresses():
        try:
            sock.sendto(b"\x00\x00\x00\x00", (bcast, MNDP_PORT))
        except OSError:
            pass

    end_time = time.monotonic() + timeout
    while True:
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([sock], [], [], remaining)
        if not ready:
            break
        data, (ip, _) = sock.recvfrom(2048)
        if ip in devices:
            continue
        if len(data) <= 4:
            # Our own discovery probe looped back with no TLV payload - not a real device.
            continue
        info = _parse_mndp_packet(data)
        devices[ip] = {
            "ipAddress": ip,
            "mac": info.get("mac"),
            "identity": info.get("identity"),
            "platform": info.get("platform"),
            "board": info.get("board"),
            "version": info.get("version"),
            "method": "mndp",
        }
    sock.close()
    return list(devices.values())


def discover_via_arp():
    """Inspect the local ARP table for hosts with a MikroTik MAC address (devices on the same Ethernet segment)."""
    devices = []
    try:
        with open("/proc/net/arp") as f:
            lines = f.readlines()[1:]
    except OSError:
        return devices

    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
        ip_address, _hw_type, flags, mac, _mask, _device = parts[:6]
        if flags == "0x0" or mac == "00:00:00:00:00:00":
            continue
        if mac.upper().startswith(_MIKROTIK_OUI_PREFIXES):
            devices.append({
                "ipAddress": ip_address,
                "mac": mac.upper(),
                "identity": None,
                "platform": "MikroTik",
                "board": None,
                "version": None,
                "method": "arp",
            })
    return devices


def probe_default_router(host="192.168.88.1"):
    """Check the MikroTik factory-default address for an open API/Winbox port."""
    for port in (8728, 8291):
        try:
            with socket.create_connection((host, port), timeout=1):
                return {
                    "ipAddress": host,
                    "mac": None,
                    "identity": None,
                    "platform": "MikroTik (default address)",
                    "board": None,
                    "version": None,
                    "method": "default-ip",
                }
        except OSError:
            continue
    return None


def discover_routers(timeout=5):
    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        mndp_f = ex.submit(discover_via_mndp, timeout)
        scan_f = ex.submit(discover_via_port_scan, timeout)
        for device in mndp_f.result():
            found[device["ipAddress"]] = device
        for device in scan_f.result():
            found.setdefault(device["ipAddress"], device)
    for device in discover_via_arp():
        found.setdefault(device["ipAddress"], device)
    default = probe_default_router()
    if default:
        found.setdefault(default["ipAddress"], default)
    return list(found.values())


def get_router_connection(ROUTER_IP,ROUTER_USERNAME,ROUTER_PASSWORD):
    connection = RouterOsApiPool(
        host=ROUTER_IP,
        username=ROUTER_USERNAME,
        password=ROUTER_PASSWORD,
        plaintext_login=True
    )
    return connection.get_api()



def create_hotspot_user(router, phone, duration_minutes, profile_name, password):
    host = router.tunnel_ip or router.ip_address
    # api = MikrotikOperation()
    api = get_router_connection(host, router.user_name, router.password)
    users = api.get_resource('/ip/hotspot/user')
    limit_uptime = f"{duration_minutes}m"

    def _add(prof):
        users.add(**{'name': phone, 'password': password,
                     'limit-uptime': limit_uptime, 'profile': prof})

    def _update():
        # We know ≥1 user exists here so .get() won't return !empty
        all_users = list(users.get())
        existing = next((u for u in all_users if u.get('name') == phone), None)
        if not existing:
            raise RuntimeError(f"User '{phone}' not found for update on {host}")
        # Log the full dict so we can see the actual key name for the ID field
        logger.info("Existing user dict for %s: %s", phone, existing)
        dot_id = existing.get('.id') or existing.get('id')
        if dot_id is None:
            # Fallback: search for any key that looks like an ID
            dot_id = next((v for k, v in existing.items() if 'id' in k.lower()), None)
        if dot_id is None:
            raise RuntimeError(f"Cannot find .id for user '{phone}' — dict: {existing}")
        users.set(**{'.id': dot_id, 'password': password,
                     'limit-uptime': limit_uptime, 'profile': profile_name})
        logger.info("Hotspot user updated: %s on %s", phone, host)

    try:
        _add(profile_name)
        logger.info("Hotspot user created: %s on %s", phone, host)
    except Exception as add_err:
        err_str = str(add_err).lower()
        if 'already have user' in err_str:
            _update()
        elif 'does not match any value of profile' in err_str:
            logger.warning("Profile '%s' not found on %s, falling back to default", profile_name, host)
            try:
                _add('default')
                logger.info("Hotspot user created with default profile: %s on %s", phone, host)
            except Exception as fallback_err:
                if 'already have user' in str(fallback_err).lower():
                    _update()
                else:
                    raise RuntimeError(f"Cannot create hotspot user '{phone}': {fallback_err}")
        else:
            raise RuntimeError(f"Cannot create hotspot user '{phone}': {add_err}")
    return phone, password

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

def remove_user_from_router(router: RouterInfo, username: str):
    host = router.tunnel_ip or router.ip_address
    api = get_router_connection(host, router.user_name, router.password)
    try:
        api.get_resource('/ip/hotspot/user').remove(**{'name': username})
    except Exception as e:
        logger.warning("Could not remove hotspot user %s: %s", username, e)
    try:
        api.get_resource('/queue/simple').remove(**{'name': username})
    except Exception:
        pass  # queue entry may not exist

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
               target=f"{username}",
               maxlimit=f"{download_speed_kbps}k/{upload_speed_kbps}k",
               priority=8)
    except Exception as e:
        return f'error occured {e}'


def generate_reg_token() -> str:
    """Generate a unique registration token for a router."""
    return uuid.uuid4().hex 


def generate_ros_script(reg_token: str, server_url: str) -> str:
    """
    Return a RouterOS script the customer pastes into their MikroTik scheduler.

    What it does:
      - Runs on every reboot
      - Sends the reg_token + router identity/board/version to the VPS
      - VPS uses this to confirm the router is online and record its public IP

    How to install on MikroTik:
      System > Scheduler > Add
        Name: netstar-register
        Start Time: startup
        Interval: 00:00:00  (run once on boot)
        On Event: <paste the script here>
    """
    register_url = f"{server_url}/api/v1/register-router"
    return f"""\
:local regToken "{reg_token}"
:local serverUrl "{register_url}"
:local identity [/system identity get name]
:local board [/system resource get board-name]
:local version [/system resource get version]
:local data ("token=" . $regToken . "&identity=" . $identity . "&board=" . $board . "&version=" . $version)
/tool fetch url=$serverUrl http-method=post http-data=$data output=none"""


def apply_wireguard_peer(public_key: str, tunnel_ip: str) -> None:
    bare_ip = tunnel_ip.split("/")[0]
    conf_path = f"/etc/wireguard/{settings.WG_INTERFACE}.conf"

    # 1. Add peer to the live kernel interface immediately
    try:
        subprocess.run(
            ["wg", "set", settings.WG_INTERFACE,
             "peer", public_key,
             "allowed-ips", f"{bare_ip}/32"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply WireGuard peer: {exc.stderr or exc}",
        )

    # 2. Persist to wg0.conf so the peer survives a reboot
    try:
        try:
            with open(conf_path, "r") as f:
                conf = f.read()
        except FileNotFoundError:
            conf = ""

        # Split on [Peer] boundaries — first part is the [Interface] section
        parts = conf.split("\n[Peer]")
        interface_section = parts[0]

        # Drop any existing block for this public key (re-registration / IP change)
        other_peers = [p for p in parts[1:] if f"PublicKey = {public_key}" not in p]

        new_peer = f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = {bare_ip}/32"

        updated = interface_section.rstrip()
        for peer in other_peers:
            updated += "\n[Peer]" + peer
        updated += new_peer + "\n"

        with open(conf_path, "w") as f:
            f.write(updated)

        logger.info("Persisted peer %s (%s/32) to %s", public_key[:10], bare_ip, conf_path)

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write {conf_path}: {exc}",
        )
 



def generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


 
ROUTEROS_SCRIPT_TEMPLATE = """\
# ============================================================
# MikroTik Hotspot + WireGuard Setup (auto-generated)
# Router ID: @@ROUTER_ID@@
# Idempotent: safe to run multiple times without "already have" errors.
# ============================================================
#
# BEFORE YOU RUN THIS:
# On flash-constrained boards (e.g. smips architecture, hAP lite), the
# "wireless" and "hotspot" packages must already be installed and match
# your RouterOS version, or this script fails at those steps.
 
:local hotspotName    "@@HOTSPOT_NAME@@"
:local hotspotDnsName "@@HOTSPOT_DNS_NAME@@"
:local wanInterface   "@@WAN_INTERFACE@@"
:local wifiCountry    "@@WIFI_COUNTRY@@"
 
:local apiUser        "@@API_USERNAME@@"
:local apiPassword    "@@API_PASSWORD@@"
 
:local tunnelIp       "@@TUNNEL_IP@@"
:local hubTunnelIp    "@@HUB_TUNNEL_IP@@"
:local hubPublicKey   "@@HUB_PUBLIC_KEY@@"
:local hubHost        "@@HUB_HOST@@"
:local hubPort        @@HUB_PORT@@
:local registerUrl    "@@CALLBACK_URL@@"
:local regToken       "@@REGISTRATION_TOKEN@@"
:local backendUrl     "@@BACKEND_URL@@"
 
# ---- 1. Scoped API user for backend automation (not 'admin') ----
:put "Step 1: Creating scoped API user..."
:if ([:len [/user group find name=api-only]] = 0) do={
  /user group add name=api-only policy=api,rest-api,read,write,ssh,ftp,test,sensitive
} else={
  /user group set [find name=api-only] policy=api,rest-api,read,write,ssh,ftp,test,sensitive
}
:if ([:len [/user find name=$apiUser]] = 0) do={
  /user add name=$apiUser password=$apiPassword group=api-only
} else={
  /user set [find name=$apiUser] password=$apiPassword group=api-only
  :put "  '$apiUser' already existed — password/group updated."
}
 
# ---- 2. Wireless ----
:put "Step 2: Configuring wireless..."
:put "  Releasing wlan1 from CAPsMAN control (harmless if it wasn't managed)..."
/interface wireless cap set enabled=no
/interface wireless set wlan1 ssid=$hotspotName mode=ap-bridge disabled=no country=$wifiCountry
 
# ---- 3. Hotspot bridge (double-bridge fix: move wlan1 off the default bridge) ----
:put "Step 3: Creating bridge-hotspot..."
:if ([:len [/interface bridge find name=bridge-hotspot]] = 0) do={
  /interface bridge add name=bridge-hotspot
}
:local correctPort [/interface bridge port find interface=wlan1 bridge=bridge-hotspot]
:if ([:len $correctPort] > 0) do={
  :put "  wlan1 is already on bridge-hotspot — nothing to do."
} else={
  :local anyPort [/interface bridge port find interface=wlan1]
  :if ([:len $anyPort] > 0) do={
    :put "  wlan1 is on a different bridge — removing it first..."
    /interface bridge port remove $anyPort
    :delay 2
  }
  :put "  Adding wlan1 to bridge-hotspot..."
  /interface bridge port add bridge=bridge-hotspot interface=wlan1
}
 
# ---- 4. IP / DHCP for hotspot clients ----
:put "Step 4: Setting up hotspot IP/DHCP..."
:if ([:len [/ip address find address=10.10.10.1/24]] = 0) do={
  /ip address add address=10.10.10.1/24 interface=bridge-hotspot
}
:if ([:len [/ip pool find name=hotspot-pool]] = 0) do={
  /ip pool add name=hotspot-pool ranges=10.10.10.10-10.10.10.254
}
:if ([:len [/ip dhcp-server find name=dhcp-hotspot]] = 0) do={
  /ip dhcp-server add name=dhcp-hotspot interface=bridge-hotspot address-pool=hotspot-pool lease-time=1h disabled=no
}
:if ([:len [/ip dhcp-server network find address=10.10.10.0/24]] = 0) do={
  /ip dhcp-server network add address=10.10.10.0/24 gateway=10.10.10.1 dns-server=8.8.8.8
}
 
# ---- 5. Hotspot profile + server ----
:put "Step 5: Creating hotspot server..."
:if ([:len [/ip hotspot profile find name=hotspot-profile]] = 0) do={
  /ip hotspot profile add name=hotspot-profile hotspot-address=10.10.10.1 dns-name=$hotspotDnsName
}
# Accept plaintext (PAP) logins so a custom login.html can submit the
# password directly, plus cookie so returning devices stay logged in.
/ip hotspot profile set [find name=hotspot-profile] login-by=http-pap,cookie
:if ([:len [/ip hotspot find name=$hotspotName]] = 0) do={
  /ip hotspot add name=$hotspotName interface=bridge-hotspot address-pool=hotspot-pool profile=hotspot-profile disabled=no
}
 
# ---- 5b. Walled garden — allow payment API access before authentication ----
:put "Step 5b: Setting up walled garden for payment..."
:if ([:len [/ip hotspot walled-garden ip find dst-address=$hubHost]] = 0) do={
  /ip hotspot walled-garden ip add dst-address=$hubHost protocol=tcp action=accept comment="platform payment API"
}
 
# ---- 5c. Cache product list from platform (host passed as query param) ----
:put "Step 5c: Caching product list..."
:if ([:len [/system scheduler find name=refresh-products]] = 0) do={
  /system scheduler add name=refresh-products interval=1h start-time=startup \
    on-event=(":local b \"" . $backendUrl . "\"\r\n:local n \"" . $hotspotDnsName . "\"\r\n/tool fetch url=(\$b . \"api/v1/get/products?host=\" . \$n) output=file dst-path=\"hotspot/products.json\"")
}
 
# ---- 6. Voucher duration profiles ----
:put "Step 6: Creating voucher profiles..."
:if ([:len [/ip hotspot user profile find name=profile-30min]] = 0) do={
  /ip hotspot user profile add name=profile-30min rate-limit=2M/2M
}
:if ([:len [/ip hotspot user profile find name=profile-1hr]] = 0) do={
  /ip hotspot user profile add name=profile-1hr rate-limit=4M/4M
}
:if ([:len [/ip hotspot user profile find name=profile-3hr]] = 0) do={
  /ip hotspot user profile add name=profile-3hr rate-limit=4M/4M
}
:if ([:len [/ip hotspot user profile find name=profile-24hr]] = 0) do={
  /ip hotspot user profile add name=profile-24hr rate-limit=6M/6M
}
:if ([:len [/ip hotspot user profile find name=profile-7day]] = 0) do={
  /ip hotspot user profile add name=profile-7day rate-limit=6M/6M
}
 
# ---- 7. NAT ----
:put "Step 7: Setting up NAT..."
:if ([:len [/ip firewall nat find chain=srcnat action=masquerade out-interface=$wanInterface]] = 0) do={
  /ip firewall nat add chain=srcnat out-interface=$wanInterface action=masquerade
}
 
# ---- 8. WireGuard: dial OUT to the hub (works behind any NAT/CGNAT) ----
:put "Step 8: Connecting to WireGuard hub..."
:if ([:len [/interface wireguard find name=wg-hub]] = 0) do={
  /interface wireguard add name=wg-hub listen-port=51820
}
:if ([:len [/ip address find address=($tunnelIp . "/32")]] = 0) do={
  /ip address add address=($tunnelIp . "/32") interface=wg-hub
}
:if ([:len [/interface wireguard peers find interface=wg-hub]] = 0) do={
  /interface wireguard peers add interface=wg-hub public-key=$hubPublicKey \\
    endpoint-address=$hubHost endpoint-port=$hubPort \\
    allowed-address=($hubTunnelIp . "/32") persistent-keepalive=25s
}
:if ([:len [/ip route find dst-address=($hubTunnelIp . "/32")]] = 0) do={
  /ip route add dst-address=($hubTunnelIp . "/32") gateway=wg-hub
}
 
# ---- 9. Certificate + REST API, reachable only over the tunnel ----
:put "Step 9: Enabling REST API..."
:if ([:len [/certificate find name=local-ca]] = 0) do={
  /certificate add name=local-ca common-name=local-ca days-valid=3650 key-usage=key-cert-sign,crl-sign
  /certificate sign local-ca ca-crl-host=$tunnelIp name=local-ca
}
:if ([:len [/certificate find name=api-cert]] = 0) do={
  /certificate add name=api-cert common-name=$tunnelIp days-valid=3650 key-usage=tls-server
  /certificate sign api-cert ca=local-ca name=api-cert
}
/ip service set www-ssl certificate=api-cert disabled=no
 
# Enable the plaintext binary API (port 8728) for backend automation.
# This is safe here because it is scoped to ONLY be reachable from the
# hub's tunnel address — never exposed to the LAN or open internet.
:if ([:len [/ip service find name=api]] > 0) do={
  /ip service set api disabled=no address=($hubTunnelIp . "/32")
}
# Also scope the encrypted API (8729) to the tunnel only, for defence in depth.
:if ([:len [/ip service find name=api-ssl]] > 0) do={
  /ip service set api-ssl disabled=no address=($hubTunnelIp . "/32")
}
# Allow SSH from the hub tunnel (for remote fleet management) AND the local
# hotspot LAN (so on-site setup isn't locked out) — but NOT the open WAN.
/ip service set ssh disabled=no address=($hubTunnelIp . "/32,10.10.10.0/24,192.168.88.0/24")
 
# ---- 10. Firewall: allow tunnel traffic BEFORE the default WAN drop rule ----
:put "Step 10: Fixing firewall rule order..."
:local dropRule [/ip firewall filter find comment="defconf: drop all not coming from LAN"]
:if ([:len $dropRule] > 0) do={
  :if ([:len [/ip firewall filter find comment="allow wireguard handshake"]] = 0) do={
    /ip firewall filter add chain=input protocol=udp dst-port=51820 action=accept place-before=$dropRule comment="allow wireguard handshake"
  }
  :if ([:len [/ip firewall filter find comment="allow hub traffic over wireguard"]] = 0) do={
    /ip firewall filter add chain=input in-interface=wg-hub action=accept place-before=$dropRule comment="allow hub traffic over wireguard"
  }
} else={
  :put "  WARNING: default WAN drop rule not found - add these manually above it:"
  :put "  /ip firewall filter add chain=input protocol=udp dst-port=51820 action=accept"
  :put "  /ip firewall filter add chain=input in-interface=wg-hub action=accept"
}
 
# ---- 11. Remove the default login.html (you'll upload your own custom page) ----
:put "Step 11: Removing default login.html..."
:if ([:len [/file find name="hotspot/login.html"]] > 0) do={
  /file remove "hotspot/login.html"
  :put "  Removed default login.html."
} else={
  :put "  No default login.html found — nothing to remove."
}
 
# ---- 12. Register this router with the platform ----
:put "Step 12: Registering with platform..."
:put "  Waiting for WireGuard tunnel to establish..."
:delay 5
:local myPublicKey [/interface wireguard get [find name=wg-hub] public-key]
:local myTunnelIp [/ip address get [find interface=wg-hub] address]

:put ""
:put "============================================================"
:put " SETUP COMPLETE - registration response from platform:"
:put "============================================================"
:put ($result->"data")
:put ""
:put "Hotspot gateway IP (clients connect here):"
:put [/ip address get [find interface=bridge-hotspot] address]
:put ""
:put "------------------------------------------------------------"
:put "If the above shows an error, add this peer to the hub manually"
:put "using the two values below (copy each line exactly):"
:put ""
:put "Public key:"
:put $myPublicKey
:put ""
:put "Tunnel IP:"
:put $myTunnelIp
:put ""
:put ""
:put "Registration Token"
:put $regToken
:put "------------------------------------------------------------"
"""

 
def render_setup_script(
    router_id: int,
    req: RouterCreate,
    tunnel_ip: str,
    api_username: str,
    api_password: str,
    registration_token: str,
    hostname: str,
    wan_interface: str,
) -> str:
    replacements = {
        "@@ROUTER_ID@@": str(router_id),
        "@@HOTSPOT_NAME@@": req.hotspot_name,
        "@@HOTSPOT_DNS_NAME@@": hostname,
        "@@WAN_INTERFACE@@": wan_interface,
        "@@WIFI_COUNTRY@@": "kenya",
        "@@API_USERNAME@@": api_username,
        "@@API_PASSWORD@@": api_password,
        "@@TUNNEL_IP@@": tunnel_ip,
        "@@HUB_PUBLIC_KEY@@": settings.HUB_PUBLIC_KEY,
        "@@HUB_HOST@@": settings.HUB_ENDPOINT_HOST,
        "@@HUB_PORT@@": str(settings.HUB_ENDPOINT_PORT),
        "@@CALLBACK_URL@@": f"{settings.CALLBACK_BASE_URL}/v1/register/callback",
        "@@REGISTRATION_TOKEN@@": registration_token,
        "@@HUB_TUNNEL_IP@@": settings.HUB_TUNNEL_IP,
        "@@BACKEND_URL@@": settings.Backend_BASE_URL,
    }
    script = ROUTEROS_SCRIPT_TEMPLATE
    for token, value in replacements.items():
        script = script.replace(token, value)
    return script
 
def allocate_tunnel_ip(db: Session) -> str:
    taken = {
        row.tunnel_ip
        for row in db.execute(select(RouterInfo.tunnel_ip).with_for_update()).all()
    }
 
    for octet in range(
        settings.TUNNEL_POOL_FIRST_HOST_OCTET,
        settings.TUNNEL_POOL_LAST_HOST_OCTET + 1,
    ):
        candidate = f"10.200.0.{octet}"
        if candidate not in taken:
            return candidate
 
    raise HTTPException(
        status_code=409,
        detail="WireGuard tunnel pool exhausted (10.200.0.0/16 is full). "
        "Expand the pool before adding more routers.",
    )
