# # setup/notifications/email.py

# from django.conf import settings
# from django.core.mail import EmailMultiAlternatives
# from django.template.loader import render_to_string


# def send_notification_email(
#     *,
#     subject,
#     template,
#     context,
#     to,
#     cc=None,
# ):
#     """
#     Send an HTML notification email.
#     """

#     html_content = render_to_string(template, context)

#     email = EmailMultiAlternatives(
#         subject=subject,
#         body="",
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         to=to,
#         cc=cc or [],
#     )

#     email.attach_alternative(html_content, "text/html")

#     email.send()

# setup/notifications/email.py

# from django.conf import settings
# from django.core.mail import EmailMultiAlternatives
# from django.template import Template, Context
# from django.template.loader import render_to_string


# def send_notification_email(
#     *,
#     subject,
#     template=None,
#     template_body=None,
#     context=None,
#     to=None,
#     cc=None,
# ):
#     """
#     Send an HTML notification email.

#     Supports:
#         1. Django template file via `template`
#         2. Database template body via `template_body`

#     `template_body` takes priority when supplied.
#     """

#     context = context or {}
#     to = to or []
#     cc = cc or []

#     # ==========================================
#     # RENDER EMAIL CONTENT
#     # ==========================================

#     if template_body is not None:
#         html_content = Template(template_body).render(Context(context))

#     elif template:
#         html_content = render_to_string(
#             template,
#             context,
#         )

#     else:
#         raise ValueError("Either template or template_body is required.")

#     # ==========================================
#     # CREATE EMAIL
#     # ==========================================

#     email = EmailMultiAlternatives(
#         subject=subject,
#         body="",
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         to=to,
#         cc=cc,
#     )

#     email.attach_alternative(
#         html_content,
#         "text/html",
#     )

#     # ==========================================
#     # SEND
#     # ==========================================

#     email.send()

#     return {
#         "success": True,
#         "html_content": html_content,
#     }

# setup/notifications/email.py

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_notification_email(
    *,
    subject,
    html_content,
    to,
    cc=None,
):
    """
    Send an HTML notification email.

    The HTML content is already rendered by the
    NotificationTemplate notification service.
    """

    email = EmailMultiAlternatives(
        subject=subject,
        body="",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
        cc=cc or [],
    )

    email.attach_alternative(
        html_content,
        "text/html",
    )

    email.send()
