from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .service import send_notification


def send_order_notification(
    *,
    notification_type,
    items,
    email_subject,
    email_template,
    sms_message,
    extra_context=None,
):
    """
    Send an order notification to unique receivers.

    Email:
        Receiver -> TO
        Sender   -> CC

    SMS:
        Receiver -> SMS
        Sender   -> SMS

    Items are grouped by receiver so that one notification
    is sent per receiver.
    """

    items = list(items)

    if not items:
        return

    grouped_items = defaultdict(list)

    for item in items:
        receiver_key = (
            item.receiver_email or "",
            item.receiver_phone or "",
        )

        grouped_items[receiver_key].append(item)

    for (receiver_email, receiver_phone), receiver_items in grouped_items.items():

        first_item = receiver_items[0]

        # --------------------------------------------
        # SMS recipients
        # Receiver + Sender
        # Remove blanks and duplicates
        # --------------------------------------------

        sms_recipients = list(
            dict.fromkeys(
                phone.strip()
                for phone in [
                    first_item.receiver_phone,
                    first_item.sender_phone,
                ]
                if phone and phone.strip()
            )
        )

        # --------------------------------------------
        # Notification context
        # --------------------------------------------

        context = {
            "receiver": first_item.receiver_name,
            "sender": first_item.sender_name,
            "items": receiver_items,
            "order": first_item.order,
            "order_no": first_item.order.order_no,
            "vendor_order_no": first_item.order.vendor_order_no,
            # ==========================================
            # FIRST ITEM DETAILS
            # Used by order status email templates
            # ==========================================
            "barcode": first_item.barcode,
            "waybill_no": first_item.waybillNo,
            "year": timezone.now().year,
        }
        if extra_context:
            context.update(extra_context)

        # --------------------------------------------
        # Send only AFTER successful transaction
        # --------------------------------------------

        transaction.on_commit(
            lambda context=context, receiver_email=receiver_email, cc_email=first_item.sender_email, sms_numbers=sms_recipients, subject=email_subject, message=sms_message: send_notification(
                notification_type=notification_type,
                context=context,
                receiver_email=receiver_email,
                cc_email=cc_email,
                sms_recipients=sms_numbers,
                email_subject=subject,
                email_template=email_template,
                sms_message=message,
            )
        )
