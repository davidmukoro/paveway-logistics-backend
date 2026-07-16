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
from django.utils.dateparse import parse_date
from logistics.models import Dispatch


class WalletFundingViewSet(AuditedModelViewSet):
    queryset = WalletFunding.objects.all().order_by("-transactionDate")
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Wallet Funding"


class TodayWalletFundingViewSet(AuditedModelViewSet):
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Today's Wallet Funding"

    def get_queryset(self):
        today = timezone.now().date()
        return WalletFunding.objects.filter(transactionDate=today).order_by("-id")


class CustomerWalletReport(AuditedModelViewSet):
    serializer_class = WalletSerializer  # Use the correct serializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Wallet Funding Report"

    def get_date_range(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        if not start_date or not end_date:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return start_date, end_date

    @action(detail=False, methods=["get"], url_path="wallet-funding-report")
    def wallet_funding_report(self, request):

        result = self.get_date_range(request)

        if isinstance(result, Response):
            return result

        start_date, end_date = result

        queryset = WalletFunding.objects.filter(
            transactionDate__range=[start_date, end_date]
        ).order_by("-id")

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


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

    @action(detail=False, methods=["get"], url_path="expense-by-category")
    def expense_by_category(self, request):

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        category_id = request.query_params.get("category")

        if not start_date or not end_date or not category_id:
            return Response(
                {"detail": "start_date, end_date and category are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)

        # =========================
        # FILTER EXPENSES
        # =========================

        qs = Expense.objects.filter(
            postedAt__range=[start_date, end_date], category_id=category_id
        ).order_by("-postedAt")

        # =========================
        # SUMMARY
        # =========================

        summary = qs.aggregate(total_amount=Sum("amount"), total_count=Count("id"))

        total_amount = summary["total_amount"] or 0
        total_count = summary["total_count"] or 0

        # =========================
        # SERIALIZE LIST
        # =========================

        data = [
            {
                "id": x.id,
                "amount": float(x.amount),
                "description": x.description,
                "expenseDate": x.expenseDate,
                "postedAt": x.postedAt,
                "postedBy": str(x.postedBy) if x.postedBy else None,
                "staff": str(x.staff.fullName) if x.staff else None,
            }
            for x in qs
        ]

        return Response(
            {
                "category": category_id,
                "start_date": start_date,
                "end_date": end_date,
                "total_amount": float(total_amount),
                "total_count": total_count,
                "data": data,
            }
        )

    @action(detail=False, methods=["get"], url_path="driver-performance")
    def driver_performance(self, request):
        start_date = parse_date(request.query_params.get("start_date"))
        end_date = parse_date(request.query_params.get("end_date"))

        start_dt = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required"},
                status=400,
            )

        # ==================================================
        # DATE-ONLY FILTER (NO TIME, NO TIMEZONE ISSUES)
        # ==================================================

        drivers = (
            Dispatch.objects.filter(assigned_at__range=[start_dt, end_dt])
            .values(
                "agent__id",
                "agent__staffNo",
                "agent__first_name",
                "agent__last_name",
            )
            .annotate(
                total_dispatches=Count("id"),
                delivered=Count("id", filter=Q(status="DELIVERED")),
                returned=Count("id", filter=Q(status="RETURNED")),
                in_transit=Count(
                    "id",
                    filter=Q(
                        status__in=[
                            "IN_TRANSIT",
                            "PICKED_UP",
                            "IN_HUB_TRANSFER",
                            "OUT_FOR_DELIVERY",
                        ]
                    ),
                ),
                issues=Count(
                    "id", filter=Q(status__in=["ISSUE", "DAMAGED", "PARTIAL"])
                ),
            )
            .order_by("-total_dispatches")
        )
        results = []

        for driver in drivers:

            total = driver["total_dispatches"] or 0
            delivered = driver["delivered"] or 0

            success_rate = round((delivered / total * 100), 2) if total else 0

            results.append(
                {
                    "driver_id": driver["agent__id"],
                    "staff_no": driver["agent__staffNo"],
                    "driver_name": f"{driver['agent__first_name']} {driver['agent__last_name']}",
                    "total_dispatches": total,
                    "delivered": delivered,
                    "returned": driver["returned"],
                    "in_transit": driver["in_transit"],
                    "issues": driver["issues"],
                    "success_rate": success_rate,
                }
            )

        return Response(results)

    @action(detail=False, methods=["get"], url_path="driver-performance-details")
    def driver_performance_details(self, request):

        driver_id = request.query_params.get("driver_id")
        start_date = parse_date(request.query_params.get("start_date"))
        end_date = parse_date(request.query_params.get("end_date"))

        start_dt = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        if not driver_id:
            return Response(
                {"detail": "driver_id is required"},
                status=400,
            )
        qs = (
            Dispatch.objects.filter(
                agent_id=driver_id,
                assigned_at__range=[start_dt, end_dt],
            )
            .select_related(
                "order_item",
                "vehicle",
                "agent",
            )
            .order_by("-assigned_at")
        )

        data = []

        for dispatch in qs:

            item = dispatch.order_item

            data.append(
                {
                    "id": dispatch.id,
                    "batch_no": dispatch.batch_no,
                    "barcode": item.barcode,
                    "sender_name": item.sender_name,
                    "receiver_name": item.receiver_name,
                    "receiver_phone": item.receiver_phone,
                    "delivery_fee": float(item.delivery_fee or 0),
                    "status": dispatch.status,
                    "assigned_at": dispatch.assigned_at,
                    "delivered_at": dispatch.delivered_at,
                    "vehicle": (dispatch.vehicle.vehicleNo if dispatch.vehicle else ""),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="vehicle-performance")
    def vehicle_performance(self, request):

        start_date = parse_date(request.query_params.get("start_date"))
        end_date = parse_date(request.query_params.get("end_date"))

        if not start_date or not end_date:
            return Response(
                {"detail": "start_date and end_date are required"},
                status=400,
            )

        start_dt = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        vehicles = (
            Dispatch.objects.filter(
                assigned_at__range=[start_dt, end_dt], vehicle__isnull=False
            )
            .values(
                "vehicle__id",
                "vehicle__vehicleNo",
                "vehicle__owner_type",
                "vehicle__logistics_partner__name",
            )
            .annotate(
                total_dispatches=Count("id"),
                delivered=Count("id", filter=Q(status="DELIVERED")),
                returned=Count("id", filter=Q(status="RETURNED")),
                in_transit=Count(
                    "id",
                    filter=Q(
                        status__in=[
                            "IN_TRANSIT",
                            "PICKED_UP",
                            "IN_HUB_TRANSFER",
                            "OUT_FOR_DELIVERY",
                        ]
                    ),
                ),
                issues=Count(
                    "id", filter=Q(status__in=["ISSUE", "DAMAGED", "PARTIAL"])
                ),
            )
            .order_by("-total_dispatches")
        )

        results = []

        for v in vehicles:

            total = v["total_dispatches"] or 0
            delivered = v["delivered"] or 0

            utilization_score = round((total / total) * 100, 2) if total else 0
            success_rate = round((delivered / total * 100), 2) if total else 0

            results.append(
                {
                    "vehicle_id": v["vehicle__id"],
                    "vehicle_no": v["vehicle__vehicleNo"],
                    "owner": v["vehicle__owner_type"],
                    "partner": (
                        v["vehicle__logistics_partner__name"]
                        if v["vehicle__logistics_partner__name"]
                        else ""
                    ),
                    "total_dispatches": total,
                    "delivered": delivered,
                    "returned": v["returned"],
                    "in_transit": v["in_transit"],
                    "issues": v["issues"],
                    "success_rate": success_rate,
                    "utilization_score": utilization_score,
                }
            )

        return Response(results)

    @action(detail=False, methods=["get"], url_path="vehicle-performance-details")
    def vehicle_performance_details(self, request):

        vehicle_id = request.query_params.get("vehicle_id")
        start_date = parse_date(request.query_params.get("start_date"))
        end_date = parse_date(request.query_params.get("end_date"))

        if not vehicle_id:
            return Response(
                {"detail": "vehicle_id is required"},
                status=400,
            )

        start_dt = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        qs = (
            Dispatch.objects.filter(
                vehicle_id=vehicle_id,
                assigned_at__range=[start_dt, end_dt],
            )
            .select_related(
                "order_item",
                "vehicle",
                "agent",
            )
            .order_by("-assigned_at")
        )

        data = []

        for d in qs:

            item = d.order_item

            data.append(
                {
                    "id": d.id,
                    "batch_no": d.batch_no,
                    "barcode": item.barcode,
                    "sender_name": item.sender_name,
                    "receiver_name": item.receiver_name,
                    "receiver_phone": item.receiver_phone,
                    "status": d.status,
                    "assigned_at": d.assigned_at,
                    "delivered_at": d.delivered_at,
                    "driver": (
                        f"{d.agent.first_name} {d.agent.last_name}" if d.agent else ""
                    ),
                    "vehicle": d.vehicle.vehicleNo if d.vehicle else "",
                }
            )

        return Response(data)
