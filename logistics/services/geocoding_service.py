# services/geocoding_service.py

from ..utils import build_clean_address, geocode_address


def build_coordinates(item_address, zone_name, lga_name, state_name):
    if not item_address:
        return None, None

    full_address = f"{item_address}, {state_name}"

    return geocode_address(build_clean_address(full_address))
