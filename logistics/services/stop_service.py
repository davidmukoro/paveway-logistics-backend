# from django.utils import timezone
# from logistics.models import DispatchStop

# FINAL_STATUSES = [
#     "DELIVERED",
#     "RETURNED",
#     "ISSUE",
# ]


# def check_stop_completion(stop):

#     incomplete = stop.dispatches.exclude(status__in=FINAL_STATUSES).exists()

#     if incomplete:
#         return False

#     stop.completed = True
#     stop.completed_at = timezone.now()

#     stop.save(
#         update_fields=[
#             "completed",
#             "completed_at",
#         ]
#     )

#     return True


# def update_stop_completion(stop):
#     """
#     Check if all dispatch items in a stop are completed.
#     """

#     pending_statuses = [
#         "PICKED_UP",
#         "IN_TRANSIT",
#         "OUT_FOR_DELIVERY",
#     ]

#     pending_items = stop.dispatches.filter(status__in=pending_statuses).exists()

#     if not pending_items:

#         if not stop.completed:
#             stop.completed = True
#             stop.completed_at = timezone.now()
#             stop.save(
#                 update_fields=[
#                     "completed",
#                     "completed_at",
#                 ]
#             )

#         return True

#     return False
from django.utils import timezone

FINAL_STATUSES = [
    "DELIVERED",
    "RETURNED",
    "ISSUE",
    "DAMAGED",
    "LOST",
]


def update_stop_completion(stop):
    """
    Mark stop completed when all parcels have reached final status.
    """

    has_pending = stop.dispatches.exclude(status__in=FINAL_STATUSES).exists()

    if has_pending:
        return False

    if not stop.completed:
        stop.completed = True
        stop.completed_at = timezone.now()

        stop.save(
            update_fields=[
                "completed",
                "completed_at",
            ]
        )

    return True
