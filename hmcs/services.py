from setup.models import User
from decimal import Decimal
from django.db import transaction

from .models import (
    PayrollPeriod,
    PayrollRecord,
    EmployeeAllowance,
    EmployeeDeduction,
)


def _to_dec(x):
    return Decimal(str(x)) if x is not None else Decimal("0.00")


@transaction.atomic
def generate_monthly_payroll(year: int, month: int, user=None, run=None):
    """
    Net Pay = monthly_pay + allowances - deductions
    Returns summary list (compatible with view)
    """

    period, _ = PayrollPeriod.objects.get_or_create(year=year, month=month)

    if period.is_closed:
        raise ValueError("Payroll period is already closed.")

    employees = User.objects.filter(is_active=True, paystaff=True)

    summary = []

    for emp in employees:
        basic_salary = _to_dec(emp.monthly_pay)

        # --- Allowances
        allowances = EmployeeAllowance.objects.filter(
            employee=emp,
            period=period,
        )
        total_allowances = sum(
            (_to_dec(a.amount) for a in allowances),
            Decimal("0.00"),
        )

        # --- Deductions
        deductions = EmployeeDeduction.objects.filter(
            employee=emp,
            period=period,
        )
        total_deductions = sum(
            (_to_dec(d.amount) for d in deductions),
            Decimal("0.00"),
        )

        # --- Net
        net_pay = basic_salary + total_allowances - total_deductions

        # --- Save record
        PayrollRecord.objects.update_or_create(
            employee=emp,
            period=period,
            defaults={
                "basic_salary": basic_salary,
                "total_allowances": total_allowances,
                "total_deductions": total_deductions,
                "net_pay": net_pay,
                "approved_by": getattr(user, "username", None),
                "run": run,
            },
        )

        summary.append(
            {
                "employee_id": str(emp.id),
                "employee_name": f"{emp.first_name} {emp.last_name}".strip(),
                "staff_no": getattr(emp, "staff_no", ""),
                "gross_monthly": float(basic_salary),  # ✅ matches your view
                "total_allowances_monthly": float(total_allowances),
                "total_deductions_monthly": float(total_deductions),
                "net_pay": float(net_pay),
            }
        )

    return summary
