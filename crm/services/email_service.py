from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_ticket_email(ticket, recipient, template, subject, context):

    if not recipient or not recipient.email:
        return

    context.update(
        {
            "customer": ticket.customer,
            "ticket": ticket,
            "company": "Paveway Logistics Limited",
            "support_email": "support@paveway-logistics.com",
            "portal_url": "https://www.paveway-logistics.com/dashboard/login",
        }
    )

    html = render_to_string(
        f"{template}",
        context,
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body="HTML Email",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient.email],
    )

    email.attach_alternative(html, "text/html")

    email.send()
