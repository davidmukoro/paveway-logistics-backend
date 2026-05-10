from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeAllowanceViewSet,
    EmployeeDeductionViewSet,
    PayrollPeriodViewSet,
    PayrollRunViewSet,
    PayrollRecordViewSet,
    PayrollReportViewSet,
)
from django.conf import settings
from django.conf.urls.static import static

router = DefaultRouter()
router.register(r"payroll-periods", PayrollPeriodViewSet, basename="payroll-periods")
router.register(
    r"employee-allowances", EmployeeAllowanceViewSet, basename="employee-allowances"
)
router.register(
    r"employee-deductions", EmployeeDeductionViewSet, basename="employee-deductions"
)

router.register(r"payrollruns", PayrollRunViewSet, basename="payroll-run")
router.register(r"payrollrecords", PayrollRecordViewSet, basename="payroll-record")
router.register(r"payroll/reports", PayrollReportViewSet, basename="payroll-reports")

urlpatterns = (
    router.urls + [] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
