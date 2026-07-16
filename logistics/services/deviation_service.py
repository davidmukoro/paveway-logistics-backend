from math import radians, sin, cos, sqrt, atan2
from django.utils import timezone

from logistics.models import (
    DispatchRoutePoint,
    RouteDeviation,
)

# deviation threshold in meters
DEVIATION_THRESHOLD = 100


def calculate_distance(
    lat1,
    lng1,
    lat2,
    lng2,
):
    """
    Haversine distance calculation
    Returns meters
    """

    earth_radius = 6371000

    lat1 = radians(lat1)
    lat2 = radians(lat2)

    delta_lat = lat2 - lat1
    delta_lng = radians(lng2 - lng1)

    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius * c


def check_route_deviation(
    session,
    latitude,
    longitude,
):

    planned_points = DispatchRoutePoint.objects.filter(stop__session=session)

    if not planned_points.exists():
        return None

    nearest_point = None
    shortest_distance = None

    for point in planned_points:

        distance = calculate_distance(
            latitude,
            longitude,
            point.latitude,
            point.longitude,
        )

        if shortest_distance is None or distance < shortest_distance:
            shortest_distance = distance
            nearest_point = point

    # ==========================================
    # DRIVER IS BACK ON PLANNED ROUTE
    # ==========================================
    if shortest_distance <= DEVIATION_THRESHOLD:

        RouteDeviation.objects.filter(
            session=session,
            status="OPEN",
        ).update(
            status="RESOLVED",
            resolved_at=timezone.now(),
        )

        return None

    # ==========================================
    # DRIVER IS OFF THE ROUTE
    # ==========================================

    existing = (
        RouteDeviation.objects.filter(
            session=session,
            status="OPEN",
        )
        .order_by("-detected_at")
        .first()
    )

    # Still deviating from the same route
    if existing:

        existing.latitude = latitude
        existing.longitude = longitude
        existing.deviation_distance = shortest_distance
        existing.save(
            update_fields=[
                "latitude",
                "longitude",
                "deviation_distance",
            ]
        )

        return existing

    # First deviation
    deviation = RouteDeviation.objects.create(
        session=session,
        agent=session.agent,
        latitude=latitude,
        longitude=longitude,
        planned_latitude=(nearest_point.latitude if nearest_point else None),
        planned_longitude=(nearest_point.longitude if nearest_point else None),
        deviation_distance=shortest_distance,
    )

    return deviation
