from rest_framework import serializers
from .models import (
    PayrollPeriod,
    PayrollRecord,
    EmployeeAllowance,
    EmployeeDeduction,
    PayrollRun,
)


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = "__all__"

    def validate(self, data):
        # Only apply this rule when creating a new record
        if self.instance is None:
            last_period = PayrollPeriod.objects.order_by("-year", "-month").first()

            if last_period and not last_period.is_closed:
                raise serializers.ValidationError(
                    f"Previous period ({last_period.month}/{last_period.year}) is not closed."
                )

        return data


class EmployeeAllowanceSerializer(serializers.ModelSerializer):
    period_name = serializers.CharField(
        source="period.payroll_period_name", read_only=True
    )
    employee_name = serializers.CharField(source="employee.fullName", read_only=True)
    allowance_name = serializers.CharField(source="allowance.name", read_only=True)

    class Meta:
        model = EmployeeAllowance
        fields = [
            "id",
            "period_name",
            "employee_name",
            "allowance_name",
            "period",
            "employee",
            "allowance",
            "amount",
            "createdBy",
            "createdAt",
        ]
        extra_kwargs = {
            "createdBy": {"required": False},
            "createdAt": {"required": False},
        }
        read_only_fields = [
            "period_name",
            "allowance_name",
            "employee_name",
        ]


class EmployeeDeductionSerializer(serializers.ModelSerializer):
    period_name = serializers.CharField(
        source="period.payroll_period_name", read_only=True
    )
    employee_name = serializers.CharField(source="employee.fullName", read_only=True)
    deduction_name = serializers.CharField(source="deduction.name", read_only=True)

    class Meta:
        model = EmployeeDeduction
        fields = [
            "id",
            "period_name",
            "employee_name",
            "deduction_name",
            "period",
            "employee",
            "deduction",
            "amount",
            "createdBy",
            "createdAt",
        ]
        extra_kwargs = {
            "createdBy": {"required": False},
            "createdAt": {"required": False},
        }
        read_only_fields = [
            "period_name",
            "deduction_name",
            "employee_name",
        ]


class PayrollRunSerializer(serializers.ModelSerializer):
    period_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = "__all__"
        read_only_fields = ("run_date", "total_gross", "total_net")

    def get_period_name(self, obj):
        """Return employee first name + last name"""
        year = getattr(obj.period, "year", "")
        month = getattr(obj.period, "month", "")
        return f"{month}/{year}".strip()


class PayrollRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.get_full_name", read_only=True
    )

    class Meta:
        model = PayrollRecord
        fields = "__all__"
        read_only_fields = ("generated_on",)
