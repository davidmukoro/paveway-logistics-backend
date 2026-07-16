from django.utils import timezone

ALLOWED_TRANSITIONS = {
    "ASSIGNED": ["PICKED_UP"],
    "PICKED_UP": ["IN_TRANSIT"],
    "IN_TRANSIT": ["OUT_FOR_DELIVERY"],
    "OUT_FOR_DELIVERY": ["DELIVERED", "ISSUE", "PART_DELIVERED"],
}


def can_transition(current, new):
    return new in ALLOWED_TRANSITIONS.get(current, [])


def update_dispatch_status(dispatch, new_status, user=None, extra=None):
    if not can_transition(dispatch.status, new_status):
        raise ValueError(f"Invalid transition {dispatch.status} → {new_status}")

    dispatch.status = new_status

    if new_status == "PICKED_UP":
        dispatch.picked_up_at = timezone.now()
        dispatch.picked_up_by = user

    if new_status == "DELIVERED":
        dispatch.delivered_at = timezone.now()

    if new_status in ["ISSUE", "PART_DELIVERED"]:
        dispatch.issue_reason = extra

    dispatch.save()
    return dispatch
