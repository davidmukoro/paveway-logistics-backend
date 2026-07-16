from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from .services.email_service import send_ticket_email
from setup.utils import AuditedModelViewSet, generate_transid
from .models import TicketDetail, Ticket
from .serializers import TicketDetailSerializer, TicketSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from setup.models import User
from django.core.cache import cache
from django.utils import timezone


# Create your views here.
class TicketViewSet(AuditedModelViewSet):
    queryset = Ticket.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer

    def get_queryset(self):
        user = self.request.user

        status = self.request.query_params.get("status")

        qs = Ticket.objects.all().order_by("-created_at")

        if user.role == "Customer":
            qs = qs.filter(customer=user)

        if status == "closed":
            qs = qs.filter(flag="closed")
        else:
            qs = qs  # .exclude(flag="closed")

        return qs

    @action(detail=True, methods=["post"])
    def send_message(self, request, pk=None):

        ticket = self.get_object()

        message = TicketDetail.objects.create(
            ticket=ticket,
            comment=request.data["message"],
            created_by=request.user,
        )

        # Determine the recipient (always notify the other party)
        if request.user == ticket.customer:
            recipient = ticket.assign_to
        else:
            recipient = ticket.customer

        # Don't notify the sender or users without an email
        if recipient and recipient != request.user and recipient.email:
            send_ticket_email(
                ticket=ticket,
                recipient=recipient,
                template="ticket_message.html",
                subject=f"New Message on Ticket {ticket.ticketno}",
                context={
                    "message": message.comment,
                    "sender": request.user.fullName,
                },
            )

        return Response(
            {
                "id": message.id,
                "message": message.comment,
                "created_by": request.user.fullName,
                "created_at": message.created_at,
            }
        )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):

        ticket = self.get_object()

        qs = ticket.messages.select_related("created_by").order_by("created_at")

        return Response(
            [
                {
                    "id": m.id,
                    "message": m.comment,
                    "created_by": m.created_by.fullName,
                    "created_at": m.created_at,
                }
                for m in qs
            ]
        )

    @action(detail=False, methods=["post"])
    def start_chat(self, request):

        user = request.user

        ticket = Ticket.objects.create(
            ticketno=generate_transid("PT"),
            customer=user,
            assign_to=user,
            issue=request.data["issue"],
            flag="pending",
            created_by=user.fullName,
            section="Logistics",
            issue_date=timezone.now().date(),
        )

        TicketDetail.objects.create(
            ticket=ticket, comment=request.data["issue"], created_by=user
        )
        serializer = self.get_serializer(ticket)
        send_ticket_email(
            ticket=ticket,
            recipient=ticket.customer,
            template="ticket_created.html",
            subject=f"Support Ticket Created - {ticket.ticketno}",
            context={},
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def typing(self, request, pk=None):

        cache.set(f"typing_{pk}_{request.user.id}", True, timeout=5)

        return Response({"success": True})

    @action(detail=True, methods=["get"])
    def typing_status(self, request, pk=None):

        ticket = self.get_object()

        users = User.objects.exclude(id=request.user.id)

        typing = False

        for user in users:
            if cache.get(f"typing_{pk}_{user.id}"):
                typing = True
                break

        return Response({"typing": typing})

    def update(self, request, *args, **kwargs):

        ticket = self.get_object()

        old_status = ticket.flag

        response = super().update(request, *args, **kwargs)

        ticket.refresh_from_db()

        new_status = ticket.flag

        if old_status != new_status:

            latest_comment = ticket.messages.order_by("-created_at").first()

            comment = (
                latest_comment.comment
                if latest_comment
                else "No additional comment was provided."
            )

            send_ticket_email(
                ticket=ticket,
                recipient=ticket.customer,
                template="ticket_status_updated.html",
                subject=f"Ticket Status Updated - {ticket.ticketno}",
                context={
                    "old_status": old_status,
                    "new_status": new_status,
                    "comment": comment,
                    "updated_by": request.user.fullName,
                    "updated_at": timezone.now(),
                },
            )

        return response


class TicketDetailViewSet(AuditedModelViewSet):
    queryset = TicketDetail.objects.select_related("ticket")
    permission_classes = [IsAuthenticated]
    serializer_class = TicketDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        ticket_id = self.request.query_params.get("ticket")

        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)

        return qs.order_by("created_at")
