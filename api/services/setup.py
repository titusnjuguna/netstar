# router_config.py
import os
import uuid
import socket
import select
import struct
import time
import ftplib
import concurrent.futures
from io import BytesIO

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
from jinja2 import Environment, FileSystemLoader
logger = logging.getLogger(__name__)

# Public base URL of this API, embedded in the captive portal page so it can
# call back into /api/hotspot/pay/{router_id}. Override via env var when deploying.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

_template_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates"))
)



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


def get_router_live_stats(host, username, password, port):
    try:
        connection = RouterOsApiPool(host, username=username, password=password, port=port)
        connection.set_timeout(5)
        api = connection.get_api()
        resource = list(api.get_resource('/system/resource').get())
        active = list(api.get_resource('/ip/hotspot/active').get())
        connection.disconnect()

        info = resource[0] if resource else {}
        total_memory = int(info.get('total-memory', 0) or 0)
        free_memory = int(info.get('free-memory', 0) or 0)
        memory_usage = round((total_memory - free_memory) / total_memory * 100) if total_memory else 0

        return {
            "status": "online",
            "cpuLoad": int(info.get('cpu-load', 0) or 0),
            "memoryUsage": memory_usage,
            "uptime": format_uptime(info.get('uptime', '')),
            "activeUsers": len(active),
        }
    except Exception:
        return {"status": "offline", "cpuLoad": 0, "memoryUsage": 0, "uptime": "0d 0h 0m", "activeUsers": 0}


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
               target=f"{username}",
               maxlimit=f"{download_speed_kbps}k/{upload_speed_kbps}k",
               priority=8)
    except Exception as e:
        return f'error occured {e}'


def generate_reg_token() -> str:
    """Generate a unique registration token for a router."""
    return uuid.uuid4().hex  # 32-char hex string, e.g. 'a3f1c2d4...'


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