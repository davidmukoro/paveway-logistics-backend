# # setup/notifications/service.py

# from django.utils import timezone

# from .email import send_notification_email
# from .sms import send_notification_sms
# from setup.models import (
#     NotificationConfig,
#     NotificationType,
#     NotificationLog,
# )


# def send_notification(
#     *,
#     notification_type,
#     context=None,
#     receiver_email=None,
#     receiver_phone=None,
#     cc_email=None,
#     sms_recipients=None,
#     email_subject=None,
#     email_template=None,
#     sms_message=None,
# ):
#     """
#     Central notification dispatcher.

#     Determines whether a notification is enabled
#     and which channel should be used.
#     """

#     context = context or {}

#     # ==========================================
#     # 1. CHECK NOTIFICATION TYPE
#     # ==========================================

#     try:
#         notification = NotificationType.objects.get(
#             code=notification_type,
#             is_active=True,
#         )

#     except NotificationType.DoesNotExist:

#         print(f"[NOTIFICATION] {notification_type} is disabled.")

#         return {
#             "success": False,
#             "reason": "notification_disabled",
#         }

#     # ==========================================
#     # 2. GET GLOBAL CHANNEL CONFIGURATION
#     # ==========================================

#     config = NotificationConfig.objects.filter(is_active=True).first()

#     if not config:

#         print("[NOTIFICATION] No active notification configuration found.")

#         return {
#             "success": False,
#             "reason": "notification_config_not_found",
#         }

#     channel = config.channel

#     print("=" * 70)
#     print("NOTIFICATION DISPATCH")
#     print(f"TYPE    : {notification.code}")
#     print(f"CHANNEL : {channel}")
#     print("=" * 70)

#     results = {}

#     # ==========================================
#     # 3. EMAIL
#     # ==========================================

#     if channel in ["EMAIL", "BOTH"]:

#         if receiver_email:

#             if not email_subject:
#                 raise ValueError("Email subject is required.")

#             if not email_template:
#                 raise ValueError("Email template is required.")

#             log = NotificationLog.objects.create(
#                 customer=None,
#                 notification_type=notification.code,
#                 channel="EMAIL",
#                 recipient=receiver_email,
#                 subject=email_subject,
#                 message=email_template,
#                 status="PENDING",
#                 provider="EMAIL",
#             )

#             try:

#                 send_notification_email(
#                     subject=email_subject,
#                     template=email_template,
#                     context=context,
#                     to=[receiver_email],
#                     cc=[cc_email] if cc_email else [],
#                 )

#                 log.status = "SENT"
#                 log.sent_at = timezone.now()

#                 log.save(
#                     update_fields=[
#                         "status",
#                         "sent_at",
#                     ]
#                 )

#                 results["email"] = True

#             except Exception as exc:

#                 log.status = "FAILED"
#                 log.error_message = str(exc)

#                 log.save(
#                     update_fields=[
#                         "status",
#                         "error_message",
#                     ]
#                 )

#                 results["email"] = False

#         else:

#             results["email"] = False

#     # ==========================================
#     # 4. SMS
#     # ==========================================

#     if channel in ["SMS", "BOTH"]:

#         sms_recipients = sms_recipients or []

#         sms_recipients = list(
#             dict.fromkeys(
#                 phone.strip() for phone in sms_recipients if phone and phone.strip()
#             )
#         )

#         if sms_recipients and sms_message:

#             sms_success = True

#             for phone in sms_recipients:

#                 log = NotificationLog.objects.create(
#                     customer=None,
#                     notification_type=notification.code,
#                     channel="SMS",
#                     recipient=phone,
#                     message=sms_message,
#                     status="PENDING",
#                     provider="XWIRELESS",
#                 )

#                 try:

#                     response = send_notification_sms(
#                         phone=phone,
#                         message=sms_message,
#                     )

#                     log.status = "SENT"
#                     log.sent_at = timezone.now()

#                     if response:
#                         log.provider_message_id = response.get(
#                             "message_id"
#                         ) or response.get("provider_message_id")

#                     log.save(
#                         update_fields=[
#                             "status",
#                             "sent_at",
#                             "provider_message_id",
#                         ]
#                     )

#                 except Exception as exc:

#                     sms_success = False

#                     log.status = "FAILED"
#                     log.error_message = str(exc)

#                     log.save(
#                         update_fields=[
#                             "status",
#                             "error_message",
#                         ]
#                     )

#             results["sms"] = sms_success

#         else:

#             results["sms"] = False

#     return {
#         "success": True,
#         "notification_type": notification.code,
#         "channel": channel,
#         "results": results,
#     }

# setup/notifications/service.py

# from django.template import Template, Context
# from django.utils import timezone

# from .email import send_notification_email
# from .sms import send_notification_sms

# from setup.models import (
#     NotificationConfig,
#     NotificationType,
#     NotificationTemplate,
#     NotificationLog,
# )


# def send_notification(
#     *,
#     notification_type,
#     context=None,
#     receiver_email=None,
#     receiver_phone=None,
#     cc_email=None,
#     sms_recipients=None,
#     # Retained for backward compatibility.
#     # Database templates now take priority.
#     email_subject=None,
#     email_template=None,
#     sms_message=None,
# ):
#     """
#     Central notification dispatcher.

#     NotificationConfig determines the channel:
#         EMAIL
#         SMS
#         BOTH

#     NotificationTemplate provides the actual content.
#     """

#     context = context or {}

#     # ==========================================
#     # 1. CHECK NOTIFICATION TYPE
#     # ==========================================

#     try:
#         notification = NotificationType.objects.get(
#             code=notification_type,
#             is_active=True,
#         )
#     except NotificationType.DoesNotExist:

#         print(f"[NOTIFICATION] {notification_type} " f"is disabled or does not exist.")

#         return {
#             "success": False,
#             "reason": "notification_disabled",
#         }

#     # ==========================================
#     # 2. GET GLOBAL CHANNEL CONFIGURATION
#     # ==========================================

#     config = NotificationConfig.objects.filter(is_active=True).first()

#     if not config:

#         print("[NOTIFICATION] No active notification " "configuration found.")

#         return {
#             "success": False,
#             "reason": "notification_config_not_found",
#         }

#     channel = config.channel

#     print("=" * 70)
#     print("NOTIFICATION DISPATCH")
#     print(f"TYPE    : {notification.code}")
#     print(f"CHANNEL : {channel}")
#     print("=" * 70)

#     results = {}

#     # ==========================================
#     # 3. EMAIL TEMPLATE
#     # ==========================================

#     email_template_obj = None

#     if channel in ["EMAIL", "BOTH"]:

#         email_template_obj = NotificationTemplate.objects.filter(
#             notification_type=notification,
#             channel="EMAIL",
#             is_active=True,
#         ).first()

#         if email_template_obj:

#             email_subject = email_template_obj.subject
#             email_template_body = email_template_obj.body

#         else:

#             email_template_body = None

#             print(
#                 f"[NOTIFICATION] No active EMAIL template "
#                 f"found for {notification.code}."
#             )

#     # ==========================================
#     # 4. SMS TEMPLATE
#     # ==========================================

#     sms_template_obj = None

#     if channel in ["SMS", "BOTH"]:

#         sms_template_obj = NotificationTemplate.objects.filter(
#             notification_type=notification,
#             channel="SMS",
#             is_active=True,
#         ).first()

#         if sms_template_obj:

#             sms_message = sms_template_obj.body

#         else:

#             print(
#                 f"[NOTIFICATION] No active SMS template "
#                 f"found for {notification.code}."
#             )

#     # ==========================================
#     # 5. EMAIL
#     # ==========================================

#     if channel in ["EMAIL", "BOTH"]:

#         if not receiver_email:

#             results["email"] = False

#         elif not email_template_obj:

#             results["email"] = False

#         else:

#             try:

#                 # ------------------------------------------
#                 # Render template first.
#                 # This is also what gets stored in the log.
#                 # ------------------------------------------

#                 rendered_email = Template(email_template_body).render(Context(context))

#                 log = NotificationLog.objects.create(
#                     customer=None,
#                     notification_type=notification.code,
#                     channel="EMAIL",
#                     recipient=receiver_email,
#                     subject=email_subject or "",
#                     message=rendered_email,
#                     status="PENDING",
#                     provider="EMAIL",
#                 )

#                 try:

#                     send_notification_email(
#                         subject=email_subject,
#                         template_body=email_template_body,
#                         context=context,
#                         to=[receiver_email],
#                         cc=[cc_email] if cc_email else [],
#                     )

#                     log.status = "SENT"
#                     log.sent_at = timezone.now()

#                     log.save(
#                         update_fields=[
#                             "status",
#                             "sent_at",
#                         ]
#                     )

#                     results["email"] = True

#                 except Exception as exc:

#                     log.status = "FAILED"
#                     log.error_message = str(exc)

#                     log.save(
#                         update_fields=[
#                             "status",
#                             "error_message",
#                         ]
#                     )

#                     results["email"] = False

#             except Exception as exc:

#                 print(f"[NOTIFICATION] Email rendering failed: {exc}")

#                 results["email"] = False

#     # ==========================================
#     # 6. SMS
#     # ==========================================

#     if channel in ["SMS", "BOTH"]:

#         sms_recipients = sms_recipients or []

#         sms_recipients = list(
#             dict.fromkeys(
#                 phone.strip() for phone in sms_recipients if phone and phone.strip()
#             )
#         )

#         if sms_template_obj and sms_recipients and sms_message:

#             sms_success = True

#             try:

#                 rendered_sms = Template(sms_message).render(Context(context))

#             except Exception as exc:

#                 print(f"[NOTIFICATION] SMS rendering failed: {exc}")

#                 sms_success = False
#                 rendered_sms = sms_message

#             if sms_success:

#                 for phone in sms_recipients:

#                     log = NotificationLog.objects.create(
#                         customer=None,
#                         notification_type=notification.code,
#                         channel="SMS",
#                         recipient=phone,
#                         message=rendered_sms,
#                         status="PENDING",
#                         provider="XWIRELESS",
#                     )

#                     try:

#                         response = send_notification_sms(
#                             phone=phone,
#                             message=rendered_sms,
#                         )

#                         log.status = "SENT"
#                         log.sent_at = timezone.now()

#                         if response:

#                             log.provider_message_id = response.get(
#                                 "message_id"
#                             ) or response.get("provider_message_id")

#                         log.save(
#                             update_fields=[
#                                 "status",
#                                 "sent_at",
#                                 "provider_message_id",
#                             ]
#                         )

#                     except Exception as exc:

#                         sms_success = False

#                         log.status = "FAILED"
#                         log.error_message = str(exc)

#                         log.save(
#                             update_fields=[
#                                 "status",
#                                 "error_message",
#                             ]
#                         )

#             results["sms"] = sms_success

#         else:

#             results["sms"] = False

#     # ==========================================
#     # 7. RETURN RESULT
#     # ==========================================

#     return {
#         "success": True,
#         "notification_type": notification.code,
#         "channel": channel,
#         "results": results,
#     }

# setup/notifications/service.py

from django.template import Template, Context
from django.utils import timezone
from setup.models import User
from .email import send_notification_email
from .sms import send_notification_sms

from setup.models import (
    NotificationConfig,
    NotificationType,
    NotificationTemplate,
    NotificationLog,
)


def render_notification_template(body, context):
    """
    Render a NotificationTemplate body using the supplied context.
    Works for both HTML email templates and SMS templates.
    """
    if not body:
        return ""

    return Template(body).render(Context(context))


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

    NotificationType:
        Determines whether the notification is active.

    NotificationConfig:
        Determines whether EMAIL, SMS or BOTH is used.

    NotificationTemplate:
        Provides the actual subject/body for each channel.

    The old email_subject, email_template and sms_message parameters
    are retained for compatibility, but the active NotificationTemplate
    is now the source of truth.
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

            # ------------------------------------------
            # Get active EMAIL template
            # ------------------------------------------

            email_template_record = NotificationTemplate.objects.filter(
                notification_type=notification,
                channel="EMAIL",
                is_active=True,
            ).first()

            if not email_template_record:
                print(
                    f"[NOTIFICATION] No active EMAIL template "
                    f"for {notification.code}"
                )

                results["email"] = False

            else:

                rendered_email_body = render_notification_template(
                    email_template_record.body,
                    context,
                )

                # Use subject supplied in context when available.
                # Otherwise fall back to the NotificationTemplate subject.
                subject = context.get("subject")

                if subject:
                    subject = render_notification_template(
                        subject,
                        context,
                    )
                else:
                    subject = render_notification_template(
                        email_template_record.subject,
                        context,
                    )
                log = NotificationLog.objects.create(
                    customer=None,
                    notification_type=notification.code,
                    channel="EMAIL",
                    recipient=receiver_email,
                    subject=subject,
                    message=rendered_email_body,
                    status="PENDING",
                    provider="EMAIL",
                )

                try:

                    send_notification_email(
                        subject=subject,
                        html_content=rendered_email_body,
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

                    print(f"[NOTIFICATION] EMAIL FAILED: {exc}")

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

        # ------------------------------------------
        # Get active SMS template
        # ------------------------------------------

        sms_template_record = NotificationTemplate.objects.filter(
            notification_type=notification,
            channel="SMS",
            is_active=True,
        ).first()

        if not sms_template_record:

            print(f"[NOTIFICATION] No active SMS template " f"for {notification.code}")

            results["sms"] = False

        elif not sms_recipients:

            results["sms"] = False

        else:

            rendered_sms_message = render_notification_template(
                sms_template_record.body,
                context,
            )

            sms_success = True

            for phone in sms_recipients:

                log = NotificationLog.objects.create(
                    customer=None,
                    notification_type=notification.code,
                    channel="SMS",
                    recipient=phone,
                    message=rendered_sms_message,
                    status="PENDING",
                    provider="XWIRELESS",
                )

                try:

                    response = send_notification_sms(
                        phone=phone,
                        message=rendered_sms_message,
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

                    print(f"[NOTIFICATION] SMS FAILED " f"({phone}): {exc}")

            results["sms"] = sms_success

    # ==========================================
    # 5. RESULT
    # ==========================================

    return {
        "success": True,
        "notification_type": notification.code,
        "channel": channel,
        "results": results,
    }


def send_bulk_notification(
    *,
    notification_type,
    users,
    context=None,
):
    """
    Send a general/campaign notification to multiple Users.

    Users are taken directly from the existing User model.

    Each recipient is passed through the existing send_notification()
    function so that:
        - NotificationType controls whether it is active
        - NotificationConfig controls EMAIL/SMS/BOTH
        - NotificationTemplate supplies the message
        - NotificationLog records each delivery
    """

    context = context or {}

    total = 0
    successful = 0
    failed = 0

    for user in users:
        total += 1

        full_name = user.fullName or user.get_user_fullname or user.email

        recipient_context = {
            **context,
            # Recipient object
            "user": user,
            # Recipient identity
            "receiver": full_name,
            "name": full_name,
            "full_name": full_name,
            # Recipient details
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "mobile": user.mobileNo,
            "mobileNo": user.mobileNo,
            "staff_no": user.staffNo,
            "role": user.role,
            "user_type": user.userType,
        }

        try:
            result = send_notification(
                notification_type=notification_type,
                context=recipient_context,
                receiver_email=user.email,
                sms_recipients=[user.mobileNo] if user.mobileNo else [],
            )

            if result.get("success"):
                successful += 1
            else:
                failed += 1

        except Exception as exc:
            failed += 1
            print(
                f"[NOTIFICATION] Bulk notification failed " f"for {user.email}: {exc}"
            )

    return {
        "success": failed == 0,
        "notification_type": notification_type,
        "total": total,
        "successful": successful,
        "failed": failed,
    }


def get_notification_recipients(
    *,
    recipient_type,
    role=None,
    hub_id=None,
    user_ids=None,
):
    """
    Resolve notification recipients from the existing User table.
    """

    users = User.objects.filter(is_active=True)

    if recipient_type == "ALL":
        return users

    if recipient_type == "CUSTOMERS":
        return users.filter(userType=User.CUSTOMER)

    if recipient_type == "STAFF":
        return users.filter(userType=User.STAFF)

    if recipient_type == "ROLE":
        if not role:
            return User.objects.none()

        return users.filter(role=role)

    if recipient_type == "HUB":
        if not hub_id:
            return User.objects.none()

        return users.filter(hub_name_id=hub_id)

    if recipient_type == "USERS":
        if not user_ids:
            return User.objects.none()

        return users.filter(id__in=user_ids)

    return User.objects.none()
