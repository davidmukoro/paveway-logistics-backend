import requests


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


import requests


def geocode_address(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }

    try:
        response = requests.get(
            url, params=params, headers={"User-Agent": "pavewaylogistics"}, timeout=10
        )

        if response.status_code != 200:
            print("Geocoding failed:", response.status_code, response.text)
            return None, None

        data = response.json()

        # ✅ CASE 1: Valid response (list)
        if isinstance(data, list) and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])

        # ✅ CASE 2: Error response (dict)
        if isinstance(data, dict):
            print("Geocoding API error:", data)
            return None, None

        # ✅ CASE 3: Empty list
        print("No results for address:", address)
        return None, None

    except Exception as e:
        print("Geocoding exception:", str(e))
        return None, None

    # utils.py OR services.py


from .models import OrderItemTracking


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
