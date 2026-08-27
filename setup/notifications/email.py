# setup/notifications/email.py

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_notification_email(
    *,
    subject,
    template,
    context,
    to,
    cc=None,
):
    """
    Send an HTML notification email.
    """

    html_content = render_to_string(template, context)

    email = EmailMultiAlternatives(
        subject=subject,
        body="",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
        cc=cc or [],
    )

    email.attach_alternative(html_content, "text/html")

    email.send()
