from django.utils import timezone
from .models import Expense, WalletFunding, IouRequest
from rest_framework import serializers
from setup.serializers import UserSerializer
from setup.models import User, ExpenseCategory
from setup.utils import generate_transid
from hmcs.models import EmployeeDeduction, AllowanceDeduction, PayrollPeriod


class WalletSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)  # Keep customer read-only

    class Meta:
        model = WalletFunding
        fields = [
            "id",
            "customer",
            "transactionDate",
            "txntype",
            "amount",
            "txnRef",
            "narration",
            "postedBy",
            "postedAt",
        ]

        extra_kwargs = {
            "id": {"read_only": True},
            "postedAt": {"read_only": True},
            "narration": {"required": False},
            "customer": {"read_only": True},
        }

    def create(self, validated_data):
        request = self.context.get("request")
        customer_id = request.data.get("customer_id")  # Extract from request

        try:
            customer = User.objects.get(id=customer_id)  # Fetch user object
        except User.DoesNotExist:
            raise serializers.ValidationError({"customer_id": "Invalid customer ID"})

        validated_data["customer"] = customer  # Assign the user object, not ID
        return super().create(validated_data)


class IouRequestSerializer(serializers.ModelSerializer):
    # staff = UserSerializer(read_only=True)  # Keep staff read-only
    staff_name = serializers.CharField(
        source="staff.fullName", read_only=True
    )  # Add staff_name field

    class Meta:
        model = IouRequest
        fields = [
            "id",
            "iouref",
            "staff",
            "approvedBy",
            "approvedAt",
            "amount",
            "staff_name",
            "reason",
            "status",
            "requestDate",
            "approvedBy",
            "approvedAt",
        ]

        extra_kwargs = {
            "id": {"read_only": True},
            "requestDate": {"required": False},
            "approvedAt": {"required": False},
            "reason": {"required": False},
            "staff_name": {"read_only": True},
            "iouref": {"required": False},
            "approvedBy": {"required": False},
        }

    def create(self, validated_data):
        request = self.context.get("request")
        staff_id = request.data.get("staff")  # Extract from request

        try:
            staff = User.objects.get(id=staff_id)  # Fetch user object
        except User.DoesNotExist:
            raise serializers.ValidationError({"staff_id": "Invalid staff ID"})

        validated_data["staff"] = staff  # Assign the user object, not ID
        validated_data["iouref"] = generate_transid("IOU")
        return super().create(validated_data)

    # ✅ THIS IS THE KEY PART
    def update(self, instance, validated_data):
        request = self.context.get("request")
        new_status = validated_data.get("status", instance.status)
        new_amt = validated_data.get("amount", instance.amount)

        # detect transition: Pending -> Approved
        if instance.status == "Pending" and new_status == "Approved":

            # 🔒 prevent duplicate expense creation
            if not Expense.objects.filter(
                description__icontains=instance.iouref
            ).exists():

                # Expense.objects.create(
                #     staff=instance.staff,
                #     amount=new_amt,
                #     description=f"IOU Approved - {instance.iouref}",
                #     expenseDate=timezone.now().date(),
                #     postedBy=request.user.fullName if request else "",
                #     postedAt=timezone.now(),
                #     category=ExpenseCategory.objects.filter(
                #         name="Iou Expense"
                #     ).first(),  # Assign IOU category, create if doesn't exist
                # )
                EmployeeDeduction.objects.create(
                    employee=instance.staff,
                    amount=new_amt,
                    # description=f"IOU Approved - {instance.iouref}",
                    period=PayrollPeriod.objects.filter(is_closed=False)
                    .order_by("-createdAt")
                    .first(),
                    createdBy=request.user.fullName if request else "",
                    createdAt=timezone.now(),
                    deduction=AllowanceDeduction.objects.filter(
                        name="Iou"
                    ).first(),  # Assign IOU category, create if doesn't exist
                )

            # update approval metadata
            # validated_data["approvedBy"] = request.user.fullName if request else ""
            # validated_data["approvedAt"] = timezone.now()

        return super().update(instance, validated_data)


#         return super().create(validated_data)
class ExpenseSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.fullName", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "staff",
            "category",
            "category_name",
            "amount",
            "staff_name",
            "description",
            "expenseDate",
            "postedBy",
            "postedAt",
        ]
