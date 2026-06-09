from rest_framework import serializers
from setup.utils import generate_staffNo, generate_transid
from .models import Ticket, TicketDetail


class TicketSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.fullName", read_only=True)
    assign_to_name = serializers.CharField(source="assign_to.fullName", read_only=True)

    class Meta:
        model = Ticket
        fields = "__all__"

        extra_kwargs = {
            "created_by": {"required": False},
            "created_at": {"required": False},
            "customer": {"required": False},
            "assign_to": {"required": False},
            "ticketno": {"required": False},
        }

    def create(self, validated_data):
        user = self.context["request"].user

        validated_data["ticketno"] = generate_transid("PT")
        validated_data["customer"] = user
        validated_data["assign_to"] = user
        validated_data["created_by"] = user.fullName

        return Ticket.objects.create(**validated_data)


class TicketDetailSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(
        source="created_by.fullName", read_only=True
    )

    class Meta:
        model = TicketDetail
        fields = "__all__"

        extra_kwargs = {
            "created_by": {"required": False},
            "created_at": {"required": False},
        }
