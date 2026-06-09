from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
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

        qs = Ticket.objects.all()

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
            ticket=ticket, comment=request.data["message"], created_by=request.user
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
