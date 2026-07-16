import requests

OSRM_BASE_URL = "https://router.project-osrm.org"


def get_route(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Generates a driving route between two GPS coordinates using
    the public OSRM server.

    Returns:
    [
        {"lat": ..., "lng": ...},
        ...
    ]
    """

    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/"
        f"{origin_lng},{origin_lat};"
        f"{dest_lng},{dest_lat}"
    )

    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return []

        geometry = data["routes"][0]["geometry"]["coordinates"]

        route = []

        for lng, lat in geometry:

            route.append(
                {
                    "lat": lat,
                    "lng": lng,
                }
            )

        return route

    except requests.RequestException as e:

        print(f"OSRM Error: {e}")

        return []
