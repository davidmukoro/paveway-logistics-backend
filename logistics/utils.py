import requests
from .models import OrderItemTracking


def normalize_vendor_payload(data, vendor_id):
    """
    Converts vendor API payload into internal order format
    """

    items = []

    for item in data.get("items", []):
        items.append(
            {
                "barcode": item.get("barcode"),
                "sender_name": item.get("sender_name"),
                "sender_phone": item.get("sender_phone"),
                "receiver_name": item.get("receiver_name"),
                "receiver_phone": item.get("receiver_phone"),
                "delivery_address": item.get("address"),
                "state": item.get("state_id"),
                "lga": item.get("lga_id"),
                "zone": item.get("zone_id"),
                "weight": item.get("weight"),
                "worth": item.get("worth"),
            }
        )

    return {
        "vendor": vendor_id,
        "vendor_order_no": data.get("order_no"),
        "source": "API",
        "items": items,
    }


def fetch_vendor_orders(vendor):
    headers = {}

    if vendor.auth_type == "BEARER":
        headers["Authorization"] = f"Bearer {vendor.api_key}"

    elif vendor.auth_type == "API_KEY":
        headers["X-API-KEY"] = vendor.api_key

    response = requests.get(
        vendor.api_base_url + "/orders", headers=headers, timeout=10
    )

    response.raise_for_status()
    return response.json()


def get_vendor_mocked_data(vendor_id):
    return {
        "order_no": "VEND-001",
        "items": [
            {
                "barcode": "ABC12332323",
                "receiver_name": "John Doe",
                "receiver_phone": "08012345678",
                "sender_name": "John Doe",
                "sender_phone": "08012345678",
                "address": "Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 3,
                "weight": 2.5,
                "worth": 4000,
            },
            {
                "barcode": "ABC12332324",
                "receiver_name": "John Doe",
                "receiver_phone": "08012345678",
                "sender_name": "John Doe",
                "sender_phone": "08012345678",
                "address": "Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 4,
                "weight": 5,
                "worth": 7000,
            },
            {
                "barcode": "ABC12332325",
                "receiver_name": "John Doe",
                "receiver_phone": "08012345678",
                "sender_name": "John Doe",
                "sender_phone": "08012345678",
                "address": "Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 3,
                "weight": 4,
                "worth": 1000,
            },
            {
                "barcode": "ABC12332325",
                "receiver_name": "Isaac Olawale",
                "receiver_phone": "08012345678",
                "sender_name": "Paul Omachi",
                "sender_phone": "08012345671",
                "address": "Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 3,
                "weight": 12,
                "worth": 15000,
            },
        ],
    }


import requests


def get_vendor_data(vendor):
    try:
        response = requests.get(
            f"{vendor.api_base_url}?vendor_id={vendor.id}",
            headers={"Authorization": f"Bearer {vendor.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        raise Exception("Vendor API timeout")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Vendor API error: {str(e)}")


import random
import string
from datetime import datetime


def generate_waybill_no(src: str) -> str:
    """
    Generate a waybill number in format: SRC-YYYYMMDD-XXXXXX
    """
    # Format date as YYYYMMDD
    formatted_date = datetime.utcnow().strftime("%Y%m%d")

    # Generate random alphanumeric string of length 6
    random_alphanumeric = "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(6)
    )

    return f"{src}-{formatted_date}-{random_alphanumeric}"


def generate_delivery_code() -> str:
    """
    Generate a 7-character alphanumeric delivery code (OTP-like)
    """
    characters = string.ascii_uppercase + string.digits

    delivery_code = "".join(random.choice(characters) for _ in range(7))

    return delivery_code


from .models import AddressCache
from django.db import transaction
import requests

# def geocode_address(address: str):
#     if not address:
#         return None, None

#     address = address.strip()

#     # =========================
#     # 1. CHECK CACHE FIRST
#     # =========================
#     cached = AddressCache.objects.filter(address__iexact=address).first()

#     if cached:
#         cached.hit_count += 1
#         cached.save(update_fields=["hit_count"])
#         return cached.latitude, cached.longitude

#     # =========================
#     # 2. CALL NOMINATIM
#     # =========================
#     url = "https://nominatim.openstreetmap.org/search"

#     params = {
#         "q": address,
#         "format": "json",
#         "limit": 1,
#         "countrycodes": "ng",
#     }

#     headers = {"User-Agent": "Paveway Logistics (support@yourcompany.com)"}

#     try:
#         res = requests.get(url, params=params, headers=headers, timeout=10)
#         data = res.json()

#         if isinstance(data, list) and data:
#             lat = float(data[0]["lat"])
#             lng = float(data[0]["lon"])
#             formatted = data[0].get("display_name")

#             # =========================
#             # 3. SAVE TO CACHE
#             # =========================
#             AddressCache.objects.create(
#                 address=address,
#                 latitude=lat,
#                 longitude=lng,
#                 formatted_address=formatted,
#             )

#             return lat, lng

#     except Exception as e:
#         print("Geocode error:", str(e))


#     return None, None


# def clean_address(item_address, lga_name=None, state_name=None):
#     parts = []

#     if item_address:
#         parts.append(item_address.strip())

#     # Only add if they are real structured admin values
#     if lga_name:
#         parts.append(lga_name.strip())

#     if state_name:
#         parts.append(state_name.strip())

#     parts.append("Nigeria")

#     # Remove duplicates while preserving order
#     seen = set()
#     cleaned = []
#     for p in parts:
#         if p and p.lower() not in seen:
#             cleaned.append(p)
#             seen.add(p.lower())


#     return ", ".join(cleaned)
def build_clean_address(item_address, state_name=None):
    parts = []

    if item_address:
        parts.append(item_address.strip())

    if state_name:
        parts.append(state_name.strip())

    parts.append("Nigeria")

    return ", ".join(parts)


def geocode_address(address):
    print("GEOCODING START:", address)

    if not address:
        # print("EMPTY ADDRESS")
        return None, None

    key = normalize_address(address)
    cached = AddressCache.objects.filter(formatted_address=key).first()

    if cached:
        # print("CACHE HIT")
        return cached.latitude, cached.longitude

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "ng",
    }

    headers = {"User-Agent": "Paveway Logistics"}

    try:
        # print("CALLING NOMINATIM...")

        response = requests.get(url, params=params, headers=headers, timeout=25)

        # print("STATUS:", response.status_code)

        data = response.json()

        # print("RESPONSE:", data[:1] if isinstance(data, list) else data)

        if isinstance(data, list) and len(data) > 0:
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])

            # print("GOT COORDS:", lat, lng)

            obj, created = AddressCache.objects.update_or_create(
                address=address,
                defaults={
                    "latitude": lat,
                    "longitude": lng,
                },
            )

            return lat, lng

    except Exception as e:
        # print("GEOCODE ERROR:", str(e))
        pass

    # print("GEOCODING FAILED")
    return None, None


from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS = 6371000


def distance_meters(lat1, lon1, lat2, lon2):

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return EARTH_RADIUS * c


def calculate_speed_mps(locations):
    """
    Returns average speed in meters/second using last GPS points.
    """
    if len(locations) < 2:
        return 0

    total_distance = 0
    total_time = 0

    for i in range(len(locations) - 1):
        p1 = locations[i]
        p2 = locations[i + 1]

        d = distance_meters(p1.latitude, p1.longitude, p2.latitude, p2.longitude)

        t = abs((p1.timestamp - p2.timestamp).total_seconds())

        if t > 0:
            total_distance += d
            total_time += t

    if total_time == 0:
        return 0

    return total_distance / total_time


import re


def normalize_address(addr):
    if not addr:
        return ""

    addr = addr.lower()
    addr = re.sub(r"[^a-z0-9]", "", addr)
    return addr


def create_tracking(
    order_item,
    stage,
    user,
    remark=None,
):
    return OrderItemTracking.objects.create(
        order_item=order_item,
        stage=stage,
        updated_by=user,
        remark=remark,
    )
