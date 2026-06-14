from logistics.models import (
    DriverDocument,
    DriverDocument,
    Vehicle,
    VehicleDocument,
    VehicleDocument,
)
from setup.utils import AuditedModelViewSet
from datetime import timedelta
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import datetime, date
from django.utils.dateparse import parse_date
from crm.models import Ticket
from django.db.models.functions import Now
from logistics.models import OrderItem, WarehouseScan
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models.functions import (
    ExtractYear,
    ExtractMonth,
    ExtractDay,
    ExtractWeek,
)
from django.db.models.expressions import RawSQL
import calendar


class DashboardViewSet(AuditedModelViewSet):
    @action(detail=False, methods=["get"], url_path="fleet-compliance-summary")
    def fleet_compliance_summary(self, request):

        today = timezone.now().date()
        expiry_limit = today + timedelta(days=60)

        docs = VehicleDocument.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lte=expiry_limit,
        )

        expired = docs.filter(expiry_date__lt=today).count()

        critical = docs.filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ).count()

        expiring_soon = docs.filter(
            expiry_date__gt=today + timedelta(days=30),
            expiry_date__lte=expiry_limit,
        ).count()

        return Response(
            {
                "expired": expired,
                "critical": critical,
                "expiring_soon": expiring_soon,
            }
        )

    @action(detail=False, methods=["get"], url_path="driver-compliance-summary")
    def driver_compliance_summary(self, request):

        today = timezone.now().date()
        expiry_limit = today + timedelta(days=60)

        docs = DriverDocument.objects.filter(
            expiry_date__isnull=False,
            expiry_date__lte=expiry_limit,
        )

        expired = docs.filter(expiry_date__lt=today).count()

        critical = docs.filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ).count()

        expiring_soon = docs.filter(
            expiry_date__gt=today + timedelta(days=30),
            expiry_date__lte=expiry_limit,
        ).count()

        return Response(
            {
                "expired": expired,
                "critical": critical,
                "expiring_soon": expiring_soon,
            }
        )

    @action(detail=False, methods=["get"], url_path="fleet-compliance")
    def fleet_compliance(self, request):

        today = timezone.now().date()
        expiry_limit = today + timedelta(days=60)

        docs = (
            VehicleDocument.objects.select_related("vehicle")
            .filter(
                expiry_date__isnull=False,
                expiry_date__lte=expiry_limit,
            )
            .order_by("expiry_date")
        )

        data = []

        for doc in docs:
            attachment_url = None

            if doc.attachment:
                attachment_url = request.build_absolute_uri(doc.attachment.url)
            days_remaining = (doc.expiry_date - today).days

            if days_remaining < 0:
                status = "EXPIRED"
            elif days_remaining <= 30:
                status = "CRITICAL"
            else:
                status = "EXPIRING_SOON"

            data.append(
                {
                    "id": doc.id,
                    "vehicle_no": doc.vehicle.vehicleNo,
                    "vehicle_type": doc.vehicle.vehicleType,
                    "document_type": doc.document_type,
                    "document_number": doc.document_number,
                    "issue_date": doc.issue_date,
                    "expiry_date": doc.expiry_date,
                    "days_remaining": days_remaining,
                    "attachment": attachment_url,
                    "status": status,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="driver-compliance")
    def driver_compliance(self, request):

        today = timezone.now().date()
        expiry_limit = today + timedelta(days=60)

        docs = (
            DriverDocument.objects.select_related("driver")
            .filter(
                expiry_date__isnull=False,
                expiry_date__lte=expiry_limit,
            )
            .order_by("expiry_date")
        )

        data = []

        for doc in docs:
            attachment_url = None

            if doc.attachment:
                attachment_url = request.build_absolute_uri(doc.attachment.url)

            days_remaining = (doc.expiry_date - today).days
            days_remaining = (doc.expiry_date - today).days

            if days_remaining < 0:
                status = "EXPIRED"
            elif days_remaining <= 30:
                status = "CRITICAL"
            else:
                status = "EXPIRING_SOON"

            data.append(
                {
                    "id": doc.id,
                    "driver_id": doc.driver.id,
                    "staff_no": doc.driver.staffNo,
                    "driver_name": f"{doc.driver.first_name} {doc.driver.last_name}",
                    "document_type": doc.document_type,
                    "document_number": doc.document_number,
                    "issue_date": doc.issue_date,
                    "expiry_date": doc.expiry_date,
                    "days_remaining": days_remaining,
                    "attachment": attachment_url,
                    "status": status,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="ticket-performance")
    def ticket_performance(self, request):

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        start_date = parse_date(start_date_str) if start_date_str else None
        end_date = parse_date(end_date_str) if end_date_str else None

        today = timezone.now().date()

        if start_date is None:
            start_date = date(today.year, 1, 1)

        if end_date is None:
            end_date = today

        start_dt = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

        tickets = Ticket.objects.filter(created_at__range=[start_dt, end_dt])

        total_tickets = tickets.count()

        pending = tickets.filter(flag="pending").count()
        assigned = tickets.filter(flag="assigned").count()
        in_progress = tickets.filter(flag="in-progress").count()
        resolved = tickets.filter(flag__in=["resolved", "closed"]).count()
        closed = tickets.filter(flag="closed").count()

        efficiency = round(((closed) / total_tickets) * 100, 2) if total_tickets else 0

        return Response(
            {
                "total_tickets": total_tickets,
                "pending": pending,
                "assigned": assigned,
                "in_progress": in_progress,
                "resolved": resolved,
                "closed": closed,
                "customer_support_efficiency": efficiency,
            }
        )

    @action(detail=False, methods=["get"], url_path="support-agent-performance")
    def support_agent_performance(self, request):

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

        agents = list(
            Ticket.objects.filter(scanned_at__range=[start_dt, end_dt])
            .values(
                "assign_to__id",
                "assign_to__fullName",
            )
            .annotate(
                total_tickets=Count("id"),
                pending=Count("id", filter=Q(flag="pending")),
                assigned=Count("id", filter=Q(flag="assigned")),
                in_progress=Count("id", filter=Q(flag="in-progress")),
                resolved=Count("id", filter=Q(flag="resolved")),
                closed=Count("id", filter=Q(flag="closed")),
            )
        )

        # ✅ compute efficiency
        for a in agents:
            total = a["total_tickets"]

            a["efficiency"] = round((a["closed"] / total) * 100, 2) if total else 0

        # ✅ sort AFTER calculation
        agents = sorted(
            agents, key=lambda x: (x["efficiency"], x["closed"]), reverse=True
        )

        # ✅ build final response correctly
        results = []

        for a in agents:
            results.append(
                {
                    "staff_id": a["assign_to__id"],
                    "staff_name": a["assign_to__fullName"],
                    "total_tickets": a["total_tickets"],
                    "pending": a["pending"],
                    "assigned": a["assigned"],
                    "in_progress": a["in_progress"],
                    "resolved": a["resolved"],
                    "closed": a["closed"],
                    "efficiency": a["efficiency"],
                }
            )

        return Response(results)

    @action(detail=False, methods=["get"], url_path="ticket-performance-details")
    def ticket_performance_details(self, request):

        staff_id = request.query_params.get("staff_id")

        if not staff_id:
            return Response(
                {"detail": "staff_id is required"},
                status=400,
            )

        tickets = (
            Ticket.objects.filter(assign_to_id=staff_id)
            .select_related(
                "customer",
                "assign_to",
            )
            .order_by("-scanned_at")
        )

        data = []

        for t in tickets:

            last_message = t.messages.last().comment if t.messages.exists() else ""

            data.append(
                {
                    "ticket_id": t.id,
                    "ticketno": t.ticketno,
                    "customer": t.customer.fullName,
                    "assigned_to": t.assign_to.fullName,
                    "issue": t.issue,
                    "status": t.flag,
                    "section": t.section,
                    "issue_date": t.issue_date,
                    "scanned_at": t.scanned_at,
                    "last_message": last_message,
                    "message_count": t.messages.count(),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="dashboard-card")
    def dashboard_summary(self, request):

        now = timezone.now()

        month_start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        total_shipments = OrderItem.objects.count()

        shipments_this_month = OrderItem.objects.filter(
            scanned_at__gte=month_start
        ).count()

        pending_shipments = OrderItem.objects.exclude(flag="DELIVERED").count()

        warehouse_items = OrderItem.objects.filter(flag="WAREHOUSE").count()

        monthly_revenue = (
            OrderItem.objects.filter(scanned_at__gte=month_start).aggregate(
                total=Sum("delivery_fee")
            )["total"]
            or 0
        )

        delivered_this_month = OrderItem.objects.filter(
            scanned_at__gte=month_start,
            flag="DELIVERED",
        ).count()

        overdue_items = 0
        overdue_48hrs = 0

        scans = WarehouseScan.objects.select_related("item").filter(
            time_out__isnull=True
        )

        for scan in scans:

            overdue_time = scan.time_in + timedelta(hours=scan.item.holding_period)

            if now > overdue_time:
                overdue_items += 1

            if now > scan.time_in + timedelta(hours=48):
                overdue_48hrs += 1

        return Response(
            {
                "cards": {
                    "total_shipments": {
                        "value": total_shipments,
                        "hint": f"{shipments_this_month:,} created this month",
                    },
                    "pending_shipments": {
                        "value": pending_shipments,
                        "hint": f"{warehouse_items:,} currently in warehouse",
                    },
                    "monthly_revenue": {
                        "value": monthly_revenue,
                        "hint": f"{delivered_this_month:,} delivered this month",
                    },
                    "total_overdue_items": {
                        "value": overdue_items,
                        "hint": f"{overdue_48hrs:,} overdue above 48 hrs",
                    },
                }
            }
        )

    # @action(detail=False, methods=["get"], url_path="dashboard_charts")
    # def dashboard_charts(self, request):

    #     range_type = request.query_params.get("range", "12M")
    #     now = timezone.now()

    #     revenue_series = []
    #     sales_series = []

    #     qs = OrderItem.objects.filter(scanned_at__isnull=False)

    #     # -------------------------
    #     # 30D
    #     # -------------------------
    #     if range_type == "30D":

    #         qs = qs.filter(scanned_at__gte=now - timedelta(days=30))

    #         data = (
    #             qs.annotate(period=RawSQL("DATE(scanned_at)", []))
    #             .values("period")
    #             .annotate(
    #                 revenue=Sum("delivery_fee"),
    #                 orders=Count("id"),
    #                 delivered=Count("id", filter=Q(flag="DELIVERED")),
    #             )
    #             .order_by("period")
    #         )

    #     # -------------------------
    #     # 90D
    #     # -------------------------
    #     elif range_type == "90D":

    #         qs = qs.filter(scanned_at__gte=now - timedelta(days=90))

    #         data = (
    #             qs.annotate(
    #                 year=RawSQL("YEAR(scanned_at)", []),
    #                 week=RawSQL("WEEK(scanned_at)", []),
    #             )
    #             .values("year", "week")
    #             .annotate(
    #                 revenue=Sum("delivery_fee"),
    #                 orders=Count("id"),
    #                 delivered=Count("id", filter=Q(flag="DELIVERED")),
    #             )
    #             .order_by("year", "week")
    #         )

    #     # -------------------------
    #     # 12M
    #     # -------------------------
    #     else:

    #         qs = qs.filter(scanned_at__gte=now - timedelta(days=365))

    #         data = (
    #             qs.annotate(
    #                 year=RawSQL("YEAR(scanned_at)", []),
    #                 month=RawSQL("MONTH(scanned_at)", []),
    #             )
    #             .values("year", "month")
    #             .annotate(
    #                 revenue=Sum("delivery_fee"),
    #                 orders=Count("id"),
    #                 delivered=Count("id", filter=Q(flag="DELIVERED")),
    #             )
    #             .order_by("year", "month")
    #         )

    #     # -------------------------
    #     # FORMAT RESPONSE
    #     # -------------------------
    #     for row in data:

    #         revenue = float(row["revenue"] or 0)
    #         orders = row["orders"] or 0
    #         delivered = row["delivered"] or 0

    #         if range_type == "30D":
    #             period = str(row["period"])

    #         elif range_type == "90D":
    #             period = f"W{row['week']}"

    #         else:
    #             period = f"{row['month']}/{row['year']}"

    #         revenue_series.append(
    #             {
    #                 "period": period,
    #                 "revenue": revenue,
    #             }
    #         )

    #         sales_series.append(
    #             {
    #                 "period": period,
    #                 "orders": orders,
    #                 "delivered": delivered,
    #             }
    #         )

    #     return Response(
    #         {
    #             "range": range_type,
    #             "revenueSeries": revenue_series,
    #             "salesTrend": sales_series,
    #             "revenueTotal": sum(x["revenue"] for x in revenue_series),
    #         }
    #     )

    @action(detail=False, methods=["get"], url_path="dashboard_charts")
    def dashboard_charts(self, request):

        from datetime import datetime, timedelta
        from django.db.models.expressions import RawSQL
        from django.db.models import Sum, Count, Q
        import calendar

        range_type = request.query_params.get("range", "12M")
        now = timezone.now()

        revenue_series = []
        sales_series = []

        qs = OrderItem.objects.filter(scanned_at__isnull=False)

        # -------------------------
        # 30D (DAILY CONTINUOUS)
        # -------------------------
        if range_type == "30D":

            start_date = now - timedelta(days=29)

            data = (
                qs.filter(scanned_at__gte=start_date)
                .annotate(day=RawSQL("DATE(scanned_at)", []))
                .values("day")
                .annotate(
                    revenue=Sum("delivery_fee"),
                    orders=Count("id"),
                    delivered=Count("id", filter=Q(flag="DELIVERED")),
                )
            )

            lookup = {str(r["day"]): r for r in data}

            for i in range(30):

                day_date = (start_date + timedelta(days=i)).date()
                key = str(day_date)

                row = lookup.get(key, {})

                revenue_series.append(
                    {
                        "period": day_date.strftime("%d %b"),
                        "revenue": float(row.get("revenue") or 0),
                    }
                )

                sales_series.append(
                    {
                        "period": day_date.strftime("%d %b"),
                        "orders": row.get("orders") or 0,
                        "delivered": row.get("delivered") or 0,
                    }
                )

        # -------------------------
        # 90D (WEEKLY CONTINUOUS)
        # -------------------------
        elif range_type == "90D":

            start_date = now - timedelta(days=63)  # ~9 weeks padding

            data = (
                qs.filter(scanned_at__gte=start_date)
                .annotate(
                    year=RawSQL("YEAR(scanned_at)", []),
                    week=RawSQL("WEEK(scanned_at)", []),
                )
                .values("year", "week")
                .annotate(
                    revenue=Sum("delivery_fee"),
                    orders=Count("id"),
                    delivered=Count("id", filter=Q(flag="DELIVERED")),
                )
            )

            lookup = {(r["year"], r["week"]): r for r in data}

            for i in range(9):

                week_start = start_date + timedelta(weeks=i)
                year = week_start.year
                week = week_start.isocalendar()[1]

                row = lookup.get((year, week), {})

                label = f"W{week}"

                revenue_series.append(
                    {
                        "period": label,
                        "revenue": float(row.get("revenue") or 0),
                    }
                )

                sales_series.append(
                    {
                        "period": label,
                        "orders": row.get("orders") or 0,
                        "delivered": row.get("delivered") or 0,
                    }
                )

        # -------------------------
        # 12M (MONTHLY CONTINUOUS)
        # -------------------------
        else:

            start_date = now - timedelta(days=365)

            data = (
                qs.filter(scanned_at__gte=start_date)
                .annotate(
                    year=RawSQL("YEAR(scanned_at)", []),
                    month=RawSQL("MONTH(scanned_at)", []),
                )
                .values("year", "month")
                .annotate(
                    revenue=Sum("delivery_fee"),
                    orders=Count("id"),
                    delivered=Count("id", filter=Q(flag="DELIVERED")),
                )
            )

            lookup = {(r["year"], r["month"]): r for r in data}

            for i in range(12):

                target = now.replace(day=1) - timedelta(days=30 * i)
                year = target.year
                month = target.month

                row = lookup.get((year, month), {})

                revenue_series.append(
                    {
                        "period": calendar.month_abbr[month],
                        "revenue": float(row.get("revenue") or 0),
                    }
                )

                sales_series.append(
                    {
                        "period": calendar.month_abbr[month],
                        "orders": row.get("orders") or 0,
                        "delivered": row.get("delivered") or 0,
                    }
                )

        return Response(
            {
                "range": range_type,
                "revenueSeries": revenue_series[::-1],
                "salesTrend": sales_series[::-1],
                "revenueTotal": sum(x["revenue"] for x in revenue_series),
            }
        )
