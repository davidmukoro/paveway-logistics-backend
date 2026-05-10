from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from hmcs.models import (
    PayrollPeriod,
    EmployeeAllowance,
    EmployeeDeduction,
    PayrollRun,
    PayrollRecord,
)
from hmcs.serializers import (
    EmployeeDeductionSerializer,
    PayrollPeriodSerializer,
    EmployeeAllowanceSerializer,
    PayrollRecordSerializer,
    PayrollRunSerializer,
)
from setup.utils import AuditedModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from decimal import Decimal
from rest_framework import viewsets
from .services import generate_monthly_payroll
from django.db.models import Sum
from setup.models import User
from collections import defaultdict
from decimal import Decimal


# Create your views here.
class PayrollPeriodViewSet(AuditedModelViewSet):
    queryset = PayrollPeriod.objects.all()
    serializer_class = PayrollPeriodSerializer
    permission_classes = [IsAuthenticated]


class EmployeeAllowanceViewSet(AuditedModelViewSet):
    queryset = EmployeeAllowance.objects.all()
    serializer_class = EmployeeAllowanceSerializer
    permission_classes = [IsAuthenticated]


class EmployeeDeductionViewSet(AuditedModelViewSet):
    queryset = EmployeeDeduction.objects.all()
    serializer_class = EmployeeDeductionSerializer
    permission_classes = [IsAuthenticated]


class PayrollRecordViewSet(AuditedModelViewSet):
    queryset = PayrollRecord.objects.all().order_by("-generated_on")
    serializer_class = PayrollRecordSerializer
    permission_classes = [IsAuthenticated]


class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all().order_by("-run_date")
    serializer_class = PayrollRunSerializer

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        payroll_run = self.get_object()
        preview = request.query_params.get("preview", "false").lower() == "true"

        if payroll_run.status == "Completed" and not preview:
            return Response(
                {"detail": "Payroll Run already completed for this period."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent duplicates
        if (
            not preview
            and PayrollRun.objects.filter(period=payroll_run.period, status="Completed")
            .exclude(id=payroll_run.id)
            .exists()
        ):
            return Response(
                {"detail": "Payroll for this period has already been completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Load settings and employees
        # settings = PayrollSetting.objects.first() or PayrollSetting.objects.create()
        employees = User.objects.filter(is_active=True, paystaff=True)
        if not employees.exists():
            return Response(
                {"detail": "No active employees found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🔹 Call service computation (this also updates PayrollRecord)
        try:
            summary = generate_monthly_payroll(
                year=payroll_run.period.year,
                month=payroll_run.period.month,
                user=request.user if request.user.is_authenticated else None,
                run=payroll_run,
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        total_gross = sum(Decimal(str(item["gross_monthly"])) for item in summary)
        total_net = sum(Decimal(str(item["net_pay"])) for item in summary)

        if preview:
            return Response(
                {
                    "preview": True,
                    "message": f"Payroll preview for {payroll_run.period}.",
                    "total_employees": len(summary),
                    "totals": {"gross": str(total_gross), "net": str(total_net)},
                    "records": summary,
                }
            )

        # 🔹 Update the PayrollRun summary only
        with transaction.atomic():
            payroll_run.total_gross = total_gross
            payroll_run.total_net = total_net
            payroll_run.status = "Completed"
            payroll_run.save()

        return Response(
            {
                "preview": False,
                "message": f"Payroll successfully completed for {payroll_run.period}.",
                "total_employees": len(summary),
                "totals": {"gross": str(total_gross), "net": str(total_net)},
            },
            status=status.HTTP_200_OK,
        )


class PayrollReportViewSet(AuditedModelViewSet):
    """
    Generate Payroll Summary or Detailed report.
    """

    permission_classes = [IsAuthenticated]
    model_label = "Payroll Report"

    @action(detail=False, methods=["get"])
    def generate(self, request):
        report_type = request.query_params.get("type", "summary")
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not (month and year):
            return Response(
                {"detail": "Month and Year are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            period = PayrollPeriod.objects.get(month=month, year=year)
        except PayrollPeriod.DoesNotExist:
            return Response(
                {"detail": "Payroll Period not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        records = PayrollRecord.objects.filter(period=period).select_related("employee")

        if not records.exists():
            return Response(
                {"detail": "No Payroll Records found for this period."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================
        # ✅ SUMMARY REPORT
        # =========================
        if report_type == "summary":
            summary_list = []

            for rec in records:
                emp = rec.employee

                gross = float((rec.basic_salary or 0) + (rec.total_allowances or 0))

                summary_list.append(
                    {
                        "emp_no": emp.staffNo,
                        "emp_name": f"{emp.first_name} {emp.last_name}".strip(),
                        "basic_salary": float(rec.basic_salary or 0),
                        "total_allowance": float(rec.total_allowances or 0),
                        "total_deduction": float(rec.total_deductions or 0),
                        "gross": gross,
                        "netpay": float(rec.net_pay or 0),
                    }
                )

            totals = {
                "total_gross": float(
                    (records.aggregate(t=Sum("basic_salary"))["t"] or Decimal("0"))
                    + (
                        records.aggregate(t=Sum("total_allowances"))["t"]
                        or Decimal("0")
                    )
                ),
                "total_netpay": float(
                    records.aggregate(t=Sum("net_pay"))["t"] or Decimal("0")
                ),
            }

            return Response(
                {
                    "type": "summary",
                    "data": summary_list,
                    "totals": totals,
                }
            )

        # =========================
        # ✅ DETAILED REPORT
        # =========================
        elif report_type == "details":
            statement_nested = []
            total_gross_sum = Decimal("0.00")
            total_net_sum = Decimal("0.00")

            for rec in records:
                emp = rec.employee

                # --- Allowances
                emp_allowances = EmployeeAllowance.objects.filter(
                    employee=emp, period=period
                )

                allowances_data = [
                    {
                        "label": ea.allowance.name,
                        "amount": float(ea.amount or 0),
                    }
                    for ea in emp_allowances
                ]

                total_allowance = sum(a["amount"] for a in allowances_data)

                # --- Deductions
                emp_deductions = EmployeeDeduction.objects.filter(
                    employee=emp, period=period
                )

                deductions_data = [
                    {
                        "label": ed.deduction.name,
                        "amount": float(ed.amount or 0),
                    }
                    for ed in emp_deductions
                ]

                total_deduction = sum(d["amount"] for d in deductions_data)

                gross = float(rec.basic_salary or 0) + total_allowance
                netpay = gross - total_deduction

                total_gross_sum += Decimal(str(gross))
                total_net_sum += Decimal(str(netpay))

                statement_nested.append(
                    {
                        "emp_no": emp.staffNo,
                        "emp_name": f"{emp.first_name} {emp.last_name}".strip(),
                        "basic_salary": float(rec.basic_salary or 0),
                        "total_allowance": float(total_allowance),
                        "total_deduction": float(total_deduction),
                        "gross": float(gross),
                        "netpay": float(netpay),
                        "allowances": allowances_data,
                        "deductions": deductions_data,
                    }
                )

            totals = {
                "total_gross": float(total_gross_sum),
                "total_netpay": float(total_net_sum),
            }

            return Response(
                {
                    "type": "details",
                    "statement_nested": statement_nested,
                    "totals": totals,
                }
            )

        return Response(
            {"detail": "Invalid report type."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["get"], url_path="my-payslip")
    def my_payslip(self, request):
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not (month and year):
            return Response(
                {"detail": "Month and Year are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ Get payroll period
        try:
            period = PayrollPeriod.objects.get(month=month, year=year)
        except PayrollPeriod.DoesNotExist:
            return Response(
                {"detail": "Payroll Period not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ✅ Get employee linked to logged-in user
        try:
            employee = request.user  # adjust if your relation differs
        except AttributeError:
            return Response(
                {"detail": "Employee profile not found for user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ✅ Get payroll record for that employee
        try:
            rec = PayrollRecord.objects.get(employee=employee, period=period)
        except PayrollRecord.DoesNotExist:
            return Response(
                {"detail": "No payroll record found for this period."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================
        # ✅ Allowances
        # =========================
        emp_allowances = EmployeeAllowance.objects.filter(
            employee=employee, period=period
        )

        allowances_data = [
            {
                "label": ea.allowance.name,
                "amount": float(ea.amount or 0),
            }
            for ea in emp_allowances
        ]

        total_allowance = sum(a["amount"] for a in allowances_data)

        # =========================
        # ✅ Deductions
        # =========================
        emp_deductions = EmployeeDeduction.objects.filter(
            employee=employee, period=period
        )

        deductions_data = [
            {
                "label": ed.deduction.name,
                "amount": float(ed.amount or 0),
            }
            for ed in emp_deductions
        ]

        total_deduction = sum(d["amount"] for d in deductions_data)

        # =========================
        # ✅ Calculations
        # =========================
        basic_salary = float(rec.basic_salary or 0)
        gross = basic_salary + total_allowance
        netpay = gross - total_deduction

        # =========================
        # ✅ Response (Payslip Style)
        # =========================
        return Response(
            {
                "type": "payslip",
                "employee": {
                    "emp_no": employee.staffNo,
                    "emp_name": f"{employee.first_name} {employee.last_name}".strip(),
                },
                "period": {
                    "month": period.month,
                    "year": period.year,
                },
                "salary": {
                    "basic_salary": basic_salary,
                    "total_allowance": total_allowance,
                    "total_deduction": total_deduction,
                    "gross_pay": gross,
                    "net_pay": netpay,
                },
                "allowances": allowances_data,
                "deductions": deductions_data,
            }
        )

    # @action(detail=False, methods=["get"], url_path="bank-schedule")
    # def bank_schedule(self, request):
    #     month = request.query_params.get("month")
    #     year = request.query_params.get("year")

    #     if not (month and year):
    #         return Response(
    #             {"detail": "Month and Year are required."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     # =========================
    #     # ✅ Get Payroll Period
    #     # =========================
    #     try:
    #         period = PayrollPeriod.objects.get(month=month, year=year)
    #     except PayrollPeriod.DoesNotExist:
    #         return Response(
    #             {"detail": "Payroll Period not found."},
    #             status=status.HTTP_404_NOT_FOUND,
    #         )

    #     # =========================
    #     # ✅ Payroll Records
    #     # =========================
    #     records = PayrollRecord.objects.filter(period=period).select_related(
    #         "employee", "period"
    #     )

    #     if not records.exists():
    #         return Response(
    #             {"detail": "No payroll records found."},
    #             status=status.HTTP_404_NOT_FOUND,
    #         )

    #     # =========================
    #     # ✅ Build Schedule
    #     # =========================
    #     payroll_data = []
    #     total_netpay = Decimal("0.00")

    #     for rec in records:
    #         employee = rec.employee

    #         netpay = Decimal(rec.net_pay or 0)
    #         total_netpay += netpay

    #         payroll_data.append(
    #             {
    #                 "staff_no": employee.staffNo,
    #                 "employee": f"{employee.first_name} {employee.last_name}".strip(),
    #                 "bank": employee.bankName,
    #                 "account_no": employee.accountNumber,
    #                 "net_pay": float(netpay),
    #             }
    #         )

    #     # =========================
    #     # ✅ Response
    #     # =========================
    #     return Response(
    #         {
    #             "type": "bank_schedule",
    #             "period": {
    #                 "month": period.month,
    #                 "year": period.year,
    #             },
    #             "total_staff": len(payroll_data),
    #             "total_netpay": float(total_netpay),
    #             "data": payroll_data,
    #         }
    #     )

    @action(detail=False, methods=["get"], url_path="bank-schedule")
    def bank_schedule(self, request):
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not (month and year):
            return Response(
                {"detail": "Month and Year are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================
        # ✅ GET PAYROLL PERIOD
        # =====================================
        try:
            period = PayrollPeriod.objects.get(month=month, year=year)
        except PayrollPeriod.DoesNotExist:
            return Response(
                {"detail": "Payroll Period not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================
        # ✅ FETCH RECORDS
        # =====================================
        records = PayrollRecord.objects.filter(period=period).select_related(
            "employee",
            "employee__bank",
            "period",
        )

        if not records.exists():
            return Response(
                {"detail": "No payroll records found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================
        # ✅ BUILD RESPONSE
        # =====================================
        payroll_data = []

        grouped_banks = defaultdict(
            lambda: {
                "total_staff": 0,
                "total_amount": Decimal("0.00"),
                "employees": [],
            }
        )

        total_netpay = Decimal("0.00")

        for rec in records:
            employee = rec.employee

            bank_name = employee.bank.name if employee.bank else "No Bank"
            account_no = employee.account_no or ""

            netpay = Decimal(rec.net_pay or 0)

            total_netpay += netpay

            row = {
                "staff_no": employee.staffNo,
                "employee": f"{employee.first_name} {employee.last_name}".strip(),
                "bank": bank_name,
                "account_no": account_no,
                "net_pay": float(netpay),
            }

            # =========================
            # ✅ FLAT DATA
            # =========================
            payroll_data.append(row)

            # =========================
            # ✅ GROUPED DATA
            # =========================
            grouped_banks[bank_name]["total_staff"] += 1
            grouped_banks[bank_name]["total_amount"] += netpay

            grouped_banks[bank_name]["employees"].append(row)

        # =====================================
        # ✅ SERIALIZE GROUPED DATA
        # =====================================
        grouped_response = []

        for bank, values in grouped_banks.items():
            grouped_response.append(
                {
                    "bank": bank,
                    "total_staff": values["total_staff"],
                    "total_amount": float(values["total_amount"]),
                    "employees": values["employees"],
                }
            )

        # =====================================
        # ✅ FINAL RESPONSE
        # =====================================
        return Response(
            {
                "type": "bank_schedule",
                "period": {
                    "month": period.month,
                    "year": period.year,
                },
                "summary": {
                    "total_staff": len(payroll_data),
                    "total_banks": len(grouped_response),
                    "total_netpay": float(total_netpay),
                },
                "data": payroll_data,
                "grouped": grouped_response,
            }
        )
