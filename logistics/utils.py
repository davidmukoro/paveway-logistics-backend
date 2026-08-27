import requests
from .models import OrderItemTracking


def normalize_vendor_payload(data, vendor_id):
    """
    Converts vendor API payload into internal order format.
    Delivery fee is calculated on the frontend using:
    - subarea
    - weight
    - pricing template
    """

    items = []

    for item in data.get("items", []):
        items.append(
            {
                "barcode": item.get("barcode"),
                "sender_name": item.get("sender_name"),
                "sender_phone": item.get("sender_phone"),
                "sender_email": item.get("sender_email"),
                "receiver_name": item.get("receiver_name"),
                "receiver_phone": item.get("receiver_phone"),
                "receiver_email": item.get("receiver_email"),
                "delivery_address": item.get("address"),
                "state": item.get("state_id"),
                "lga": item.get("lga_id"),
                "zone": item.get("zone_id"),
                "subarea": item.get("subarea_id"),
                "weight": item.get("weight"),
                "worth": item.get("worth"),
                # Will be calculated before saving
                "delivery_fee": 0,
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
                "barcode": "API100001",
                "receiver_name": "John Doe",
                "receiver_phone": "08012345678",
                "receiver_email": "john.doe@example.com",
                "sender_name": "Paul Omachi",
                "sender_phone": "08012345671",
                "sender_email": "paul.omachi@example.com",
                "address": "15 Allen Avenue, Ikeja, Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 3,
                "subarea_id": 1,
                "weight": 2.5,
                "worth": 4000,
                "description": "Documents",
            },
            {
                "barcode": "API100002",
                "receiver_name": "Mary Johnson",
                "receiver_phone": "08023456789",
                "receiver_email": "mary.johnson@example.com",
                "sender_name": "David Okoro",
                "sender_phone": "08023456780",
                "sender_email": "david.okoro@example.com",
                "address": "25 Opebi Road, Ikeja, Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 4,
                "subarea_id": 2,
                "weight": 5,
                "worth": 7000,
                "description": "Clothing",
            },
            {
                "barcode": "API100003",
                "receiver_name": "Isaac Olawale",
                "receiver_phone": "08034567890",
                "receiver_email": "isaac.olawale@example.com",
                "sender_name": "Paul Omachi",
                "sender_phone": "08034567801",
                "sender_email": "paul.omachi@example.com",
                "address": "10 Acme Road, Ikeja, Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 3,
                "subarea_id": 1,
                "weight": 4,
                "worth": 1000,
                "description": "Small Package",
            },
            {
                "barcode": "API100004",
                "receiver_name": "Sarah Williams",
                "receiver_phone": "08045678901",
                "receiver_email": "sarah.williams@example.com",
                "sender_name": "Michael Ade",
                "sender_phone": "08045678902",
                "sender_email": "michael.ade@example.com",
                "address": "18 Toyin Street, Ikeja, Lagos",
                "state_id": 1,
                "lga_id": 1,
                "zone_id": 4,
                "subarea_id": 2,
                "weight": 8,
                "worth": 12500,
                "description": "Electronics",
            },
            {
                "barcode": "API100005",
                "receiver_name": "Peter James",
                "receiver_phone": "08056789012",
                "receiver_email": "peter.james@example.com",
                "sender_name": "Grace Emmanuel",
                "sender_phone": "08056789013",
                "sender_email": "grace.emmanuel@example.com",
                "address": "12 Gbagada Expressway, Gbagada, Lagos",
                "state_id": 1,
                "lga_id": 2,
                "zone_id": 5,
                "subarea_id": 3,
                "weight": 10,
                "worth": 18000,
                "description": "Household Items",
            },
            {
                "barcode": "API100006",
                "receiver_name": "Blessing Okafor",
                "receiver_phone": "08067890123",
                "receiver_email": "blessing.okafor@example.com",
                "sender_name": "Henry Obi",
                "sender_phone": "08067890124",
                "sender_email": "henry.obi@example.com",
                "address": "7 Admiralty Way, Lekki, Lagos",
                "state_id": 1,
                "lga_id": 3,
                "zone_id": 6,
                "subarea_id": 4,
                "weight": 3.5,
                "worth": 8500,
                "description": "Shoes",
            },
            {
                "barcode": "API100007",
                "receiver_name": "Daniel Musa",
                "receiver_phone": "08078901234",
                "receiver_email": "daniel.musa@example.com",
                "sender_name": "Samuel Peter",
                "sender_phone": "08078901235",
                "sender_email": "samuel.peter@example.com",
                "address": "22 Abeokuta Road, Sango, Ogun",
                "state_id": 1,
                "lga_id": 4,
                "zone_id": 7,
                "subarea_id": 5,
                "weight": 2,
                "worth": 6000,
                "description": "Books",
            },
            {
                "barcode": "API100008",
                "receiver_name": "Esther Ibrahim",
                "receiver_phone": "08089012345",
                "receiver_email": "esther.ibrahim@example.com",
                "sender_name": "Joseph Michael",
                "sender_phone": "08089012346",
                "sender_email": "joseph.michael@example.com",
                "address": "14 Sapon Road, Abeokuta, Ogun",
                "state_id": 1,
                "lga_id": 4,
                "zone_id": 7,
                "subarea_id": 6,
                "weight": 6,
                "worth": 9500,
                "description": "Kitchen Items",
            },
            {
                "barcode": "API100009",
                "receiver_name": "Emeka Nwosu",
                "receiver_phone": "08090123456",
                "receiver_email": "emeka.nwosu@example.com",
                "sender_name": "Chinedu Okeke",
                "sender_phone": "08090123457",
                "sender_email": "chinedu.okeke@example.com",
                "address": "8 Independence Layout, Enugu",
                "state_id": 1,
                "lga_id": 5,
                "zone_id": 8,
                "subarea_id": 7,
                "weight": 7.5,
                "worth": 22000,
                "description": "Computer Accessories",
            },
            {
                "barcode": "API100010",
                "receiver_name": "Aisha Bello",
                "receiver_phone": "08101234567",
                "receiver_email": "aisha.bello@example.com",
                "sender_name": "Musa Abdullahi",
                "sender_phone": "08101234568",
                "sender_email": "musa.abdullahi@example.com",
                "address": "5 Wuse II, Abuja",
                "state_id": 1,
                "lga_id": 6,
                "zone_id": 9,
                "subarea_id": 8,
                "weight": 15,
                "worth": 30000,
                "description": "Office Equipment",
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
