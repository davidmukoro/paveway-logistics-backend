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
