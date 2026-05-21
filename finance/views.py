from django.shortcuts import render
from rest_framework import viewsets, permissions
from .utils import compute_customer_wallet_balance
from .models import Expense, IouRequest, WalletFunding
from setup.models import User
from .serializers import ExpenseSerializer, IouRequestSerializer, WalletSerializer
from logistics.serializers import OrderItemSerializer
from rest_framework import generics
from rest_framework.views import APIView
from django.db.models import Sum, Count, Q
from rest_framework.response import responses, Response
from setup.utils import AuditedModelViewSet
from django.utils.dateparse import parse_date
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
from logistics.models import OrderItem
from hmcs.models import PayrollRun
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import Count
from decimal import Decimal
from django.db.models import Sum
from django.utils.dateparse import parse_date
from collections import defaultdict


class WalletFundingViewSet(AuditedModelViewSet):
    queryset = WalletFunding.objects.all().order_by("-transactionDate")
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Wallet Funding"


class CustomerWalletBalance(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        # user = User.objects.get(pk=id)
        # if user.cPayType == "Postpaid":
        #     expense = (
        #         WalletFunding.objects.filter(customer_id=id).aggregate(
        #             total=Sum("amount")
        #         )["total"]
        #         or 0.00
        #     )
        #     total_balance = float(user.creditLimit) + float(expense)
        # else:
        #     total_balance = (
        #         WalletFunding.objects.filter(customer_id=id).aggregate(
        #             total=Sum("amount")
        #         )["total"]
        #         or 0.00
        #     )
        total_balance = compute_customer_wallet_balance(id)
        return Response({"customer_id": id, "total_balance": total_balance})


class WalletTransactions(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        user = User.objects.get(pk=id)
        expense = WalletFunding.objects.filter(customer=user).order_by(
            "-transactionDate"
        )
        serializer = WalletSerializer(expense, many=True)

        return Response(serializer.data, status=200)


class IouRequestViewSet(AuditedModelViewSet):
    queryset = IouRequest.objects.all().order_by("-requestDate")
    serializer_class = IouRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "IOU Request"


class MyIouRequests(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        user = User.objects.get(pk=id)
        iou_requests = IouRequest.objects.filter(staff=user).order_by("-requestDate")
        serializer = IouRequestSerializer(iou_requests, many=True)
        return Response(serializer.data, status=200)


class ExpenseViewSet(AuditedModelViewSet):
    queryset = Expense.objects.all().order_by("-expenseDate")
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Expense"


class ReportViewSet(AuditedModelViewSet):

    def get_date_range(self, request):

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        return start_date, end_date

    @action(detail=False, methods=["get"], url_path="profit-loss")
    def profit_loss(self, request):

        result = self.get_date_range(request)

        if isinstance(result, Response):
            return result

        start_date, end_date = result

        # =========================
        # REVENUE
        # =========================

        revenue = OrderItem.objects.filter(
            scanned_at__range=[start_date, end_date]
        ).aggregate(total=Sum("delivery_fee"))["total"] or Decimal("0.00")

        returned_revenue = OrderItem.objects.filter(
            scanned_at__range=[start_date, end_date],
            flag="RETURNED",
        ).aggregate(total=Sum("delivery_fee"))["total"] or Decimal("0.00")

        gross_revenue = revenue - returned_revenue

        # =========================
        # EXPENSES (FIXED)
        # =========================

        expense_total = Expense.objects.filter(
            postedAt__range=[start_date, end_date]
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # =========================
        # PAYROLL (FIXED)
        # =========================

        payroll_total = PayrollRun.objects.filter(
            run_date__range=[start_date, end_date]  # date
        ).aggregate(total=Sum("total_net"))["total"] or Decimal("0.00")

        total_expenses = expense_total + payroll_total

        net_profit = gross_revenue - total_expenses

        # =========================
        # KPI
        # =========================

        expense_ratio = (total_expenses / gross_revenue * 100) if gross_revenue else 0
        profit_margin = (net_profit / gross_revenue * 100) if gross_revenue else 0
        payroll_ratio = (payroll_total / gross_revenue * 100) if gross_revenue else 0

        # =========================
        # PREVIOUS PERIOD (FIXED)
        # =========================

        days_diff = (end_date - start_date).days

        previous_start = start_date - timedelta(days=days_diff + 1)
        previous_end = start_date - timedelta(days=1)

        previous_revenue = OrderItem.objects.filter(
            scanned_at__range=[previous_start, previous_end]
        ).aggregate(total=Sum("delivery_fee"))["total"] or Decimal("0.00")

        revenue_growth = (
            ((revenue - previous_revenue) / previous_revenue) * 100
            if previous_revenue
            else 0
        )

        # =========================
        # MONTHLY TREND
        # =========================

        # =========================
        # MONTHLY TREND (SAFE)
        # =========================

        revenue_map = defaultdict(float)
        expense_map = defaultdict(float)

        # -------------------------
        # REVENUE GROUPING
        # -------------------------

        revenue_rows = OrderItem.objects.filter(
            scanned_at__range=[start_date, end_date]
        ).values("scanned_at", "delivery_fee")

        for row in revenue_rows:

            if row["scanned_at"]:

                month_key = row["scanned_at"].strftime("%b %Y")

                revenue_map[month_key] += float(row["delivery_fee"] or 0)

        # -------------------------
        # EXPENSE GROUPING
        # -------------------------

        expense_rows = Expense.objects.filter(
            postedAt__range=[start_date, end_date]
        ).values("postedAt", "amount")

        for row in expense_rows:

            if row["postedAt"]:

                month_key = row["postedAt"].strftime("%b %Y")

                expense_map[month_key] += float(row["amount"] or 0)

        # -------------------------
        # TREND DATA
        # -------------------------

        all_months = sorted(set(revenue_map.keys()) | set(expense_map.keys()))

        trend_data = []

        for month in all_months:

            revenue_value = revenue_map.get(month, 0)
            expense_value = expense_map.get(month, 0)

            trend_data.append(
                {
                    "month": month,
                    "revenue": revenue_value,
                    "expenses": expense_value,
                    "profit": revenue_value - expense_value,
                }
            )

        # =========================
        # EXPENSE DISTRIBUTION
        # =========================

        expense_distribution = (
            Expense.objects.filter(postedAt__range=[start_date, end_date])
            .values("category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        expense_distribution_data = [
            {
                "name": item["category__name"] or "Others",
                "value": float(item["total"] or 0),
            }
            for item in expense_distribution
        ]

        return Response(
            {
                "start_date": start_date,
                "end_date": end_date,
                "revenue": float(revenue),
                "returned_revenue": float(returned_revenue),
                "gross_revenue": float(gross_revenue),
                "expense_total": float(expense_total),
                "payroll_total": float(payroll_total),
                "total_expenses": float(total_expenses),
                "net_profit": float(net_profit),
                "expense_ratio": round(expense_ratio, 2),
                "profit_margin": round(profit_margin, 2),
                "payroll_ratio": round(payroll_ratio, 2),
                "revenue_growth": round(revenue_growth, 2),
                "trend_data": trend_data,
                "expense_distribution": expense_distribution_data,
            }
        )

    @action(detail=False, methods=["get"], url_path="expense-analysis")
    def expense_analysis(self, request):

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        # ==========================================
        # TOTAL EXPENSE
        # ==========================================

        total_expense = Expense.objects.filter(
            postedAt__range=[start_date, end_date]
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # ==========================================
        # CATEGORY BREAKDOWN
        # ==========================================

        category_expenses = (
            Expense.objects.filter(postedAt__range=[start_date, end_date])
            .values("category__name")
            .annotate(
                total=Sum("amount"),
                count=Count("id"),
            )
            .order_by("-total")
        )

        category_data = []

        for item in category_expenses:

            total = float(item["total"] or 0)

            percentage = (total / float(total_expense)) * 100 if total_expense else 0

            category_data.append(
                {
                    "category": item["category__name"] or "Others",
                    "total": total,
                    "count": item["count"],
                    "percentage": round(percentage, 2),
                }
            )

        # ==========================================
        # MONTHLY EXPENSE TREND
        # ==========================================

        monthly_map = defaultdict(float)

        expense_rows = Expense.objects.filter(
            postedAt__range=[start_date, end_date]
        ).values("postedAt", "amount")

        for row in expense_rows:

            if row["postedAt"]:

                month_key = row["postedAt"].strftime("%b %Y")

                monthly_map[month_key] += float(row["amount"] or 0)

        trend_data = [
            {
                "month": month,
                "amount": amount,
            }
            for month, amount in monthly_map.items()
        ]

        # ==========================================
        # TOP EXPENSE CATEGORY
        # ==========================================

        top_category = category_data[0] if category_data else None

        return Response(
            {
                "start_date": start_date,
                "end_date": end_date,
                "total_expense": float(total_expense),
                "top_category": top_category,
                "category_breakdown": category_data,
                "trend_data": trend_data,
            }
        )
