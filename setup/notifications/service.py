# setup/notifications/service.py

from django.utils import timezone

from .email import send_notification_email
from .sms import send_notification_sms
from setup.models import (
    NotificationConfig,
    NotificationType,
    NotificationLog,
)


def send_notification(
    *,
    notification_type,
    context=None,
    receiver_email=None,
    receiver_phone=None,
    cc_email=None,
    sms_recipients=None,
    email_subject=None,
    email_template=None,
    sms_message=None,
):
    """
    Central notification dispatcher.

    Determines whether a notification is enabled
    and which channel should be used.
    """

    context = context or {}

    # ==========================================
    # 1. CHECK NOTIFICATION TYPE
    # ==========================================

    try:
        notification = NotificationType.objects.get(
            code=notification_type,
            is_active=True,
        )

    except NotificationType.DoesNotExist:

        print(f"[NOTIFICATION] {notification_type} is disabled.")

        return {
            "success": False,
            "reason": "notification_disabled",
        }

    # ==========================================
    # 2. GET GLOBAL CHANNEL CONFIGURATION
    # ==========================================

    config = NotificationConfig.objects.filter(is_active=True).first()

    if not config:

        print("[NOTIFICATION] No active notification configuration found.")

        return {
            "success": False,
            "reason": "notification_config_not_found",
        }

    channel = config.channel

    print("=" * 70)
    print("NOTIFICATION DISPATCH")
    print(f"TYPE    : {notification.code}")
    print(f"CHANNEL : {channel}")
    print("=" * 70)

    results = {}

    # ==========================================
    # 3. EMAIL
    # ==========================================

    if channel in ["EMAIL", "BOTH"]:

        if receiver_email:

            if not email_subject:
                raise ValueError("Email subject is required.")

            if not email_template:
                raise ValueError("Email template is required.")

            log = NotificationLog.objects.create(
                customer=None,
                notification_type=notification.code,
                channel="EMAIL",
                recipient=receiver_email,
                subject=email_subject,
                message=email_template,
                status="PENDING",
                provider="EMAIL",
            )

            try:

                send_notification_email(
                    subject=email_subject,
                    template=email_template,
                    context=context,
                    to=[receiver_email],
                    cc=[cc_email] if cc_email else [],
                )

                log.status = "SENT"
                log.sent_at = timezone.now()

                log.save(
                    update_fields=[
                        "status",
                        "sent_at",
                    ]
                )

                results["email"] = True

            except Exception as exc:

                log.status = "FAILED"
                log.error_message = str(exc)

                log.save(
                    update_fields=[
                        "status",
                        "error_message",
                    ]
                )

                results["email"] = False

        else:

            results["email"] = False

    # ==========================================
    # 4. SMS
    # ==========================================

    if channel in ["SMS", "BOTH"]:

        sms_recipients = sms_recipients or []

        sms_recipients = list(
            dict.fromkeys(
                phone.strip() for phone in sms_recipients if phone and phone.strip()
            )
        )

        if sms_recipients and sms_message:

            sms_success = True

            for phone in sms_recipients:

                log = NotificationLog.objects.create(
                    customer=None,
                    notification_type=notification.code,
                    channel="SMS",
                    recipient=phone,
                    message=sms_message,
                    status="PENDING",
                    provider="XWIRELESS",
                )

                try:

                    response = send_notification_sms(
                        phone=phone,
                        message=sms_message,
                    )

                    log.status = "SENT"
                    log.sent_at = timezone.now()

                    if response:
                        log.provider_message_id = response.get(
                            "message_id"
                        ) or response.get("provider_message_id")

                    log.save(
                        update_fields=[
                            "status",
                            "sent_at",
                            "provider_message_id",
                        ]
                    )

                except Exception as exc:

                    sms_success = False

                    log.status = "FAILED"
                    log.error_message = str(exc)

                    log.save(
                        update_fields=[
                            "status",
                            "error_message",
                        ]
                    )

            results["sms"] = sms_success

        else:

            results["sms"] = False

    return {
        "success": True,
        "notification_type": notification.code,
        "channel": channel,
        "results": results,
    }
