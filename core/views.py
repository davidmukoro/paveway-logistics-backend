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
from logistics.models import OrderItem, WarehouseScan, Dispatch, Order
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models.functions import (
    ExtractYear,
    ExtractMonth,
    ExtractDay,
    ExtractWeek,
)
from django.db.models.expressions import RawSQL
import calendar
from django.db.models.functions import Coalesce
from django.db.models import Value, DecimalField


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

        role = request.user.userType

        now = timezone.now()

        month_start = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        # ======================================
        # BASE QUERYSET
        # ======================================

        orderitems = OrderItem.objects.all()

        warehouse_scans = WarehouseScan.objects.select_related("item").filter(
            time_out__isnull=True
        )

        if role == "Customer":

            orderitems = orderitems.filter(order__vendor=request.user)

            warehouse_scans = warehouse_scans.filter(item__order__vendor=request.user)

        # ======================================
        # TOTAL SHIPMENTS
        # ======================================

        total_shipments = orderitems.count()

        # ======================================
        # THIS MONTH
        # ======================================

        shipments_this_month = orderitems.filter(scanned_at__gte=month_start).count()

        # ======================================
        # PENDING
        # ======================================

        pending_shipments = orderitems.exclude(flag="DELIVERED").count()

        # ======================================
        # WAREHOUSE
        # ======================================

        warehouse_items = orderitems.filter(flag="WAREHOUSE").count()

        # ======================================
        # MONTHLY REVENUE
        # ======================================

        monthly_revenue = (
            orderitems.filter(scanned_at__gte=month_start).aggregate(
                total=Sum("delivery_fee")
            )["total"]
            or 0
        )

        # ======================================
        # DELIVERED THIS MONTH
        # ======================================

        delivered_this_month = orderitems.filter(
            scanned_at__gte=month_start,
            flag="DELIVERED",
        ).count()

        # ======================================
        # OVERDUE ITEMS
        # ======================================

        overdue_items = 0

        max_overdue_hours = 0

        for scan in warehouse_scans:

            overdue_time = scan.time_in + timedelta(hours=scan.item.holding_period)

            if now > overdue_time:

                overdue_items += 1

                extra_hours = round((now - overdue_time).total_seconds() / 3600)

                if extra_hours > max_overdue_hours:

                    max_overdue_hours = extra_hours

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
                        "hint": f"Longest overdue by {max_overdue_hours} hrs",
                    },
                }
            }
        )

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

    @action(detail=False, methods=["get"], url_path="dashboard_top_metrics")
    def rankings(self, request):

        # ====================================
        # TOP DISPATCHERS
        # ====================================

        dispatchers = (
            Dispatch.objects.values(
                "agent",
                "agent__fullName",
                "agent__hub_name__hubName",
            )
            .annotate(
                total_drops=Count("id"),
                delivered=Count("id", filter=Q(status="DELIVERED")),
            )
            .order_by("-total_drops")[:5]
        )

        top_dispatchers = []

        for dispatcher in dispatchers:

            total = dispatcher["total_drops"]
            delivered = dispatcher["delivered"]

            completion = 0

            if total:
                completion = round((delivered / total) * 100)

            top_dispatchers.append(
                {
                    "name": dispatcher["agent__fullName"],
                    "subtitle": (
                        f'{dispatcher["agent__hub_name__hubName"] or "No Hub"} '
                        f"• {completion}% completed"
                    ),
                    "value": total,
                    "progress": completion,
                }
            )

        # ====================================
        # TOP CUSTOMERS
        # ====================================

        customers = list(
            OrderItem.objects.values(
                "order__vendor",
                "order__vendor__fullName",
            )
            .annotate(
                shipments=Count("id"),
                total_amount=Coalesce(
                    Sum("delivery_fee"),
                    Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
            )
            .order_by("-total_amount")[:5]
        )

        max_amount = 1

        if customers:
            max_amount = customers[0]["total_amount"] or 1

        top_customers = []

        for customer in customers:

            progress = round(
                (float(customer["total_amount"]) / float(max_amount)) * 100
            )

            top_customers.append(
                {
                    "name": customer["order__vendor__fullName"],
                    "subtitle": (f'{customer["shipments"]:,} shipments'),
                    "value": customer["total_amount"],
                    "progress": progress,
                }
            )

        # ====================================
        # TOP HUBS
        # ====================================

        hubs = list(
            Dispatch.objects.values(
                "agent__hub_name",
                "agent__hub_name__hubName",
            )
            .annotate(
                total=Count("id"), delivered=Count("id", filter=Q(status="DELIVERED"))
            )
            .order_by("-total")[:5]
        )

        max_total = 1

        if hubs:
            max_total = hubs[0]["total"] or 1

        top_hubs = []

        for hub in hubs:

            total = hub["total"]

            delivered = hub["delivered"]

            speed = 0

            if total:
                speed = round((delivered / total) * 100)

            top_hubs.append(
                {
                    "name": hub["agent__hub_name__hubName"],
                    "subtitle": (f"{total:,} handled • {speed}% delivered"),
                    "value": total,
                    "progress": speed,
                }
            )

        return Response(
            {
                "top_dispatchers": top_dispatchers,
                "top_customers": top_customers,
                "top_hubs": top_hubs,
            }
        )

    @action(detail=False, methods=["get"], url_path="dashboard_exception_metrics")
    def dashboard_operations(self, request):

        # ======================================================
        # DRIVER EXCEPTIONS (from Dispatch issues/statuses)
        # ======================================================

        exceptions = (
            Dispatch.objects.filter(
                status__in=["DAMAGED", "PARTIAL", "RETURNED", "ISSUE"]
            )
            .values("agent__fullName", "status", "issue_reason")
            .annotate(occurrences=Count("id"))
            .order_by("-occurrences")[:5]
        )

        driver_exceptions = []

        for item in exceptions:

            count = item["occurrences"]

            severity = "High" if count >= 10 else "Medium" if count >= 5 else "Low"

            driver_exceptions.append(
                {
                    "driver": item["agent__fullName"],
                    "route": item["status"],
                    "reason": item["issue_reason"] or "No reason provided",
                    "count": count,
                    "severity": severity,
                }
            )

        # ======================================================
        # FLEET UTILIZATION (BASED ON VEHICLE MODEL - BEST APPROACH)
        # ======================================================

        vehicles = (
            Dispatch.objects.values(
                "vehicle__id",
                "vehicle__vehicleTag",
                "vehicle__vehicleNo",
            )
            .annotate(
                total_dispatches=Count("id"),
                active_dispatches=Count(
                    "id", filter=Q(status__in=["ASSIGNED", "PICKED_UP"])
                ),
                completed=Count("id", filter=Q(status="DELIVERED")),
            )
            .order_by("-total_dispatches")[:5]
        )
        fleet_utilization = []

        for v in vehicles:

            total = v["total_dispatches"]

            active = v["active_dispatches"]

            utilization = 0

            if total:
                utilization = round((active / total) * 100)
            vehicle_no = v.get("vehicle__vehicleNo") or ""
            vehicle_tag = v.get("vehicle__vehicleTag") or ""

            display_name = vehicle_no

            if vehicle_tag:
                display_name = f"{vehicle_no} ({vehicle_tag})"

            fleet_utilization.append(
                {
                    "hub": display_name,
                    "active": active,
                    "available": total - active,
                    "maintenance": 0,
                    "utilization": utilization,
                }
            )

        # ======================================================
        # OVERDUE ITEMS (OrderItem + Dispatch timing)
        # ======================================================

        overdue_queryset = (
            OrderItem.objects.filter(
                dispatch__status__in=["ASSIGNED", "PICKED_UP"],
                dispatch__delivered_at__isnull=True,
            )
            .select_related("order", "order__vendor", "dispatch")
            .order_by("dispatch__assigned_at")[:5]
        )
        overdue_items = []

        now = timezone.now()

        total_overdue = (
            OrderItem.objects.filter(
                dispatch__status__in=["ASSIGNED", "PICKED_UP"],
                dispatch__delivered_at__isnull=True,
            )
            .select_related("order", "order__vendor", "dispatch")
            .order_by("dispatch__assigned_at")
        ).count()

        for item in overdue_queryset:

            # fallback safety
            # created = getattr(item, "scanned_at", None)
            created = item.dispatch.assigned_at
            if not created:
                continue

            hours = round((now - created).total_seconds() / 3600)

            severity = (
                "Critical" if hours >= 72 else "Warning" if hours >= 24 else "Normal"
            )

            overdue_items.append(
                {
                    "item": getattr(item, "barcode", str(item.id)),
                    "owner": item.order.vendor.fullName,
                    "overdueHours": hours,
                    "severity": severity,
                }
            )

        # ======================================================
        # RESPONSE
        # ======================================================

        return Response(
            {
                "driver_exceptions": driver_exceptions,
                "fleet_utilization": fleet_utilization,
                "total_overdue": total_overdue,
                "overdue_items": overdue_items,
            }
        )

    @action(detail=False, methods=["get"], url_path="customer-shipment-trend")
    def customer_shipment_trend(self, request):

        from datetime import timedelta
        from collections import defaultdict

        range_type = request.query_params.get("range", "12M")

        now = timezone.now()

        queryset = OrderItem.objects.select_related("order")

        if request.user.userType == "Customer":

            queryset = queryset.filter(order__vendor_id=request.user.id)

        # -------------------------
        # 30 DAYS
        # -------------------------

        if range_type == "30D":

            start_date = now - timedelta(days=30)

            queryset = queryset.filter(scanned_at__gte=start_date)

            daily = defaultdict(
                lambda: {
                    "orders": 0,
                    "delivered": 0,
                    "expense": 0,
                }
            )

            for item in queryset:

                key = item.scanned_at.strftime("%d %b")

                daily[key]["orders"] += 1

                if item.flag == "DELIVERED":
                    daily[key]["delivered"] += 1

                daily[key]["expense"] += float(item.delivery_fee or 0)

            return Response(
                [
                    {
                        "period": k,
                        **v,
                    }
                    for k, v in daily.items()
                ]
            )

        # -------------------------
        # 90 DAYS
        # -------------------------

        elif range_type == "90D":

            start_date = now - timedelta(days=90)

            queryset = queryset.filter(scanned_at__gte=start_date)

            monthly = defaultdict(
                lambda: {
                    "orders": 0,
                    "delivered": 0,
                    "expense": 0,
                }
            )

            for item in queryset:

                key = item.scanned_at.strftime("%b")

                monthly[key]["orders"] += 1

                if item.flag == "DELIVERED":

                    monthly[key]["delivered"] += 1

                monthly[key]["expense"] += float(item.delivery_fee or 0)

            return Response(
                [
                    {
                        "period": k,
                        **v,
                    }
                    for k, v in monthly.items()
                ]
            )

        # -------------------------
        # 12 MONTHS
        # -------------------------

        else:

            start_date = now - timedelta(days=365)

            queryset = queryset.filter(scanned_at__gte=start_date)

            monthly = defaultdict(
                lambda: {
                    "orders": 0,
                    "delivered": 0,
                    "expense": 0,
                }
            )

            for item in queryset:

                key = item.scanned_at.strftime("%b")

                monthly[key]["orders"] += 1

                if item.flag == "DELIVERED":

                    monthly[key]["delivered"] += 1

                monthly[key]["expense"] += float(item.delivery_fee or 0)

            ordered_months = [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ]

            result = []

            for month in ordered_months:

                result.append(
                    {
                        "period": month,
                        **monthly[month],
                    }
                )

            return Response(result)

    @action(detail=False, methods=["get"], url_path="customer-status-mix")
    def customer_status_mix(self, request):

        queryset = OrderItem.objects.all()

        # -----------------------------
        # CUSTOMER FILTER
        # -----------------------------
        if request.user.userType == "Customer":
            queryset = queryset.filter(order__vendor_id=request.user.id)

        # -----------------------------
        # GROUP STATUS FROM DB
        # -----------------------------
        status_counts = queryset.values("flag").annotate(total=Count("id"))

        # -----------------------------
        # MAP DB STATUS → UI STATUS
        # -----------------------------
        status_map = {
            "DELIVERED": "Delivered",
            "IN_TRANSIT": "In Transit",
            "SCANNED_IN": "Pending Pickup",
            "WAREHOUSE": "Pending Pickup",
            "OUT_FOR_DELIVERY": "In Transit",
            "PENDING": "Pending Pickup",
            "INWARD_RETURNED": "Cancelled",
            "OUTWARD_RETURNED": "Cancelled",
        }

        result_dict = {}

        # initialize all expected buckets
        for label in [
            "Delivered",
            "In Transit",
            "Pending Pickup",
            "Delayed",
            "Cancelled",
        ]:
            result_dict[label] = 0

        # -----------------------------
        # BUILD RESULT
        # -----------------------------
        for row in status_counts:

            raw_status = row["flag"]
            count = row["total"]

            label = status_map.get(raw_status, "Delayed")

            result_dict[label] += count

        # -----------------------------
        # FORMAT RESPONSE
        # -----------------------------
        result = [{"name": k, "value": v} for k, v in result_dict.items()]

        return Response(result)

    from collections import defaultdict

    @action(detail=False, methods=["get"], url_path="shipment-aging")
    def shipment_aging(self, request):

        now = timezone.now()

        queryset = OrderItem.objects.select_related("order", "dispatch")

        # -----------------------------
        # CUSTOMER FILTER
        # -----------------------------
        if request.user.userType == "Customer":
            queryset = queryset.filter(order__vendor_id=request.user.id)

        # -----------------------------
        # BUCKETS
        # -----------------------------
        buckets = {
            "0-24h": 0,
            "24-48h": 0,
            "48-72h": 0,
            "72h+": 0,
        }

        total = 0

        for item in queryset:

            # prefer dispatch time if available, else fallback to scan time
            start_time = None

            if (
                hasattr(item, "dispatch")
                and item.dispatch
                and item.dispatch.assigned_at
            ):
                start_time = item.dispatch.assigned_at
            else:
                start_time = item.scanned_at

            if not start_time:
                continue

            hours = (now - start_time).total_seconds() / 3600

            total += 1

            if hours <= 24:
                buckets["0-24h"] += 1
            elif hours <= 48:
                buckets["24-48h"] += 1
            elif hours <= 72:
                buckets["48-72h"] += 1
            else:
                buckets["72h+"] += 1

        result = [{"name": k, "value": v} for k, v in buckets.items()]

        return Response({"total": total, "data": result})

    @action(detail=False, methods=["get"], url_path="top-destination-lga")
    def top_destination_lga(self, request):

        queryset = OrderItem.objects.select_related("lga", "order")

        # -----------------------------
        # CUSTOMER FILTER
        # -----------------------------
        if request.user.userType == "Customer":
            queryset = queryset.filter(order__vendor_id=request.user.id)
            total_all = queryset.count()

        # -----------------------------
        # GROUP BY LGA
        # -----------------------------
        top_lgas = (
            queryset.values("lga__name")  # adjust if your field differs
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )

        result = []

        for row in top_lgas:
            result.append(
                {
                    "name": row["lga__name"] or "Unknown",
                    "value": row["total"],
                    "percentage": round((row["total"] / total_all) * 100, 1),
                }
            )

        return Response(result)
