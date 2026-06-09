from django.db import models
from setup.models import User


# Create your models here.
class Ticket(models.Model):
    ticketno = models.CharField(max_length=50)
    customer = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="user_ticket"
    )
    issue = models.TextField()
    issue_date = models.DateField(blank=True, null=True)
    assign_to = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="user_assign_to"
    )
    flag = models.CharField(
        max_length=50, default="pending"
    )  # pending, assigned,in-progress,resolved,closed
    section = models.CharField(max_length=100, blank=True, null=True)
    created_by = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now_add=True)
    last_updated_by = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.ticketno


class TicketDetail(models.Model):
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="messages"
    )
    comment = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    is_read = models.BooleanField(default=False)

    is_typing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.ticket.ticketno
