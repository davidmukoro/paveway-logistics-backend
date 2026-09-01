from django.urls import path
from . import views
from .views import (
    ActiveDispatchSession,
    # AgentMovementTrail,
    AllMyDispatchView,
    CompleteDeliveryView,
    CreateDispatchRoute,
    CreateOrderView,
    DispatchStopItemsView,
    DispatchedOrderView,
    DriverDocumentViewSet,
    MyDispatchView,
    RouteComplianceSummary,
    RouteDeviationHistory,
    ScanItemView,
    OverdueItemsView,
    UpdateAgentLocation,
    UpdateDeliveryExceptionView,
    UpdateDeliveryStatus,
    UpdateDeliveryStatusView,
    UpdateDispatcherStatusView,
    VehicleDocumentViewSet,
    VendorFetchView,
    OrderUploadPreviewView,
    WarehouseScanView,
    WaybillHistory,
    RouteReplayView,
)
from .views import (
    DispatcherListView,
    ValidateBarcodeView,
    DriverPickupUpdateView,
    ManifestView,
    PartnerCreateView,
    PartnerDetailView,
    DispatchSummaryView,
    BulkDispatchView,
    dispatcherPickupView,
    DriverPickupCreateView,
    SingleDispatchView,
    VehicleDetailView,
    VehicleListCreateView,
    OrderByStatusView,
    HubViewSet,
    HubTransferViewSet,
    HubItemDetailView,
    HubstoreViewSet,
    ValidateHubBarcodeView,
    create_order_with_wallet_deduction,
    UpdateDeliveryStatusFlag,
    OrderItemTrackingView,
    TrackWayBill,
    WarehouseScanViewSet,
    PendingWarehouseScanReportView,
    TodayRunView,
    LiveDispatchers,
    StartDispatchSession,
    StopDispatchSession,
    TodayRunStopsView,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"hubs", HubViewSet, basename="hub")
router.register(r"hubtxns", HubTransferViewSet, basename="hubtxn")
router.register(r"hubstore", HubstoreViewSet, basename="hub-store")
router.register(r"warehouse-scan", WarehouseScanViewSet)
router.register(
    r"vehicle-documents",
    VehicleDocumentViewSet,
    basename="vehicle-documents",
)

router.register(
    r"driver-documents",
    DriverDocumentViewSet,
    basename="driver-documents",
)


urlpatterns = router.urls + [
    path(
        "pending-warehouse-scan/",
        PendingWarehouseScanReportView.as_view(),
        name="pending-warehouse-scan-report",
    ),
    path(
        "order-with-wallet/",
        views.create_order_with_wallet_deduction,
        name="order-wallet",
    ),
    path("create/", CreateOrderView.as_view()),
    path("my-waybill-history/", WaybillHistory.as_view()),
    path("track-my-orders/", OrderItemTrackingView.as_view()),
    path(
        "track-my-orders/<str:search>/",
        OrderItemTrackingView.as_view(),
    ),
    path("track-waybill/<str:waybill>/", TrackWayBill.as_view()),
    path("vendor-fetch/", VendorFetchView.as_view()),
    path("upload-preview/", OrderUploadPreviewView.as_view()),
    path("warehouse/scan/", WarehouseScanView.as_view()),
    path("orderStatus/", OrderByStatusView.as_view()),
    path("dispatchedOrder/", DispatchedOrderView.as_view()),
    path(
        "dispatch/pickup/", dispatcherPickupView.as_view()
    ),  # transfrom from whse to pickup
    path("pickup-summary/", DispatchSummaryView.as_view()),
    path("validate-barcode/", ValidateBarcodeView.as_view()),
    path("validate-hub-barcode/", ValidateHubBarcodeView.as_view()),
    path(
        "driver-pickup/create/",
        DriverPickupCreateView.as_view(),
        name="driver-pickup-create",
    ),
    path("dispatch-info/<str:batchno>/", views.getDispatchInfo, name="dispatch-info"),
    path("manifest/<str:batch_no>/", ManifestView.as_view(), name="manifest"),
    path("driver-pickup/update/<str:batch_no>/", DriverPickupUpdateView.as_view()),
    path("my-hub-transfer/", HubItemDetailView.as_view()),
    path("scan/", ScanItemView.as_view()),
    path("overdue/", OverdueItemsView.as_view()),
    path("partners/", PartnerCreateView.as_view()),
    path("partners/<int:pk>/", PartnerDetailView.as_view()),
    path("dispatchers/", DispatcherListView.as_view()),
    path("dispatchers/<str:pk>/", UpdateDispatcherStatusView.as_view()),
    path("vehicles/", VehicleListCreateView.as_view()),
    path("vehicles/<int:pk>/", VehicleDetailView.as_view()),
    path("dispatch/bulk/", BulkDispatchView.as_view()),
    path("dispatch/", SingleDispatchView.as_view()),  # optional
    path("my-dispatch/", MyDispatchView.as_view()),  # optional
    path("all-my-dispatches/", AllMyDispatchView.as_view()),  # optional
    path("today-run/", TodayRunView.as_view()),
    path("update-status/", UpdateDeliveryStatus.as_view()),  # optional
    path("update-status-bulk/", UpdateDeliveryStatusFlag.as_view()),  # optional
    path("agent/update-agent-location/", UpdateAgentLocation.as_view()),  # optional
    path("agent/start-dispatch-session/", StartDispatchSession.as_view()),  # optional
    path("agent/end-dispatch-session/", StopDispatchSession.as_view()),  # optional
    path("agent/active-dispatch-session/", ActiveDispatchSession.as_view()),  # optional
    # path("agent/movement-trail/", AgentMovementTrail.as_view()),  # optional
    path("agent/live-dispatchers/", LiveDispatchers.as_view()),
    path("agent/route-replay/<int:session_id>/", RouteReplayView.as_view()),
    path(
        "dispatch/create-route/",
        CreateDispatchRoute.as_view(),
        name="create-dispatch-route",
    ),
    path("agent/deviation-history/", RouteDeviationHistory.as_view()),
    path(
        "agent/route-compliance/",
        RouteComplianceSummary.as_view(),
    ),
    path("agent/today-run-stops/", TodayRunStopsView.as_view()),
    path(
        "dispatch/complete-delivery/",
        CompleteDeliveryView.as_view(),
        name="complete-delivery",
    ),
    path(
        "dispatch-stop/<int:stop_id>/items/",
        DispatchStopItemsView.as_view(),
        name="dispatch-stop-items",
    ),
    path(
        "dispatch/update-exception/",
        UpdateDeliveryExceptionView.as_view(),
        name="update-delivery-exception",
    ),
    path("dispatch-item/<uuid:item_id>/status/", UpdateDeliveryStatusView.as_view()),
]
