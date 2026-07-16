from . import views
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import CustomerWalletBalance, WalletTransactions, MyIouRequests
from .views import (
    WalletFundingViewSet,
    IouRequestViewSet,
    ExpenseViewSet,
    ReportViewSet,
    TodayWalletFundingViewSet,
    CustomerWalletReport,
)

router = DefaultRouter()
router.register(r"wallet-funding", WalletFundingViewSet, basename="wallet-funding")
router.register(r"iou-requests", IouRequestViewSet, basename="iou-requests")
router.register(r"expenses", ExpenseViewSet, basename="expenses")
router.register(r"reports", ReportViewSet, basename="reports")
router.register(r"wallet-report", CustomerWalletReport, basename="wallet-report")


urlpatterns = router.urls + [
    path(
        "customer-wallet-balance/<uuid:id>/",
        CustomerWalletBalance.as_view(),
        name="customer-wallet-balance",
    ),
    path(
        "customer-wallet-transactions/<uuid:id>/",
        WalletTransactions.as_view(),
        name="customer-wallet-transactions",
    ),
    path("my-iou-requests/<uuid:id>/", MyIouRequests.as_view(), name="my-iou-requests"),
    path(
        "today-wallet-funding/",
        TodayWalletFundingViewSet.as_view({"get": "list"}),
        name="today-wallet-funding",
    ),
]
