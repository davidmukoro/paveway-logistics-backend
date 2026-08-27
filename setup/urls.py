from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    ActiveUserSessionsView,
    BackendUserView,
    ChangePasswordView,
    CreateUserView,
    LgaViewSet,
    NotificationConfigView,
    NotificationLogListView,
    NotificationTypeViewSet,
    PasswordResetRequestView,
    PasswordResetView,
    PayGateway,
    ResetUserPasswordView,
    StateViewSet,
    TerminateSessionView,
    UpdateProfileView,
    ZoneViewSet,
    audit_report,
    GetAllStaff,
    CreateAdminPermissionView,
    AssigningPermissions,
    getUserPermission,
    UpdateStaffView,
    StaffView,
    getUserInfo,
    StaffDetailView,
    UpdatePermissionView,
    GetAllCustomer,
    UpdateCustomerProfile,
    UpdateMyProfile,
    AuditLogViewSet,
    BankViewSet,
    ExpenseCategoryViewSet,
    AllowanceDeductionViewSet,
    PricingViewSet,
)

# RoleViewSet, UserViewSet, StaffProfileViewSet,DepartmentViewSet,audit_report
from django.urls import path

router = DefaultRouter()
router.register(r"nig-states", StateViewSet)
router.register(r"lgas", LgaViewSet)
router.register(r"zones", ZoneViewSet)
router.register(r"banks", BankViewSet)
router.register(r"expense-categories", ExpenseCategoryViewSet)
router.register(r"allowance-deductions", AllowanceDeductionViewSet)
router.register(r"audit-logs", AuditLogViewSet, basename="audit-logs")
router.register(r"pricing-template", PricingViewSet)
router.register(r"staff", StaffView, basename="staff")
router.register(
    r"notifications/types", NotificationTypeViewSet, basename="notification-type"
)
# router.register(r'users', UserViewSet)
# router.register(r'staff-profiles', StaffProfileViewSet)
# router.register(r'departments', DepartmentViewSet)


urlpatterns = router.urls + [
    path("pay-gateway/", PayGateway.as_view(), name="payment-gateway"),
    path("register/", CreateUserView.as_view(), name="register"),
    # path("staff/", StaffView.as_view()),
    path("staff/<uuid:id>/", StaffDetailView.as_view()),
    path("registerStaff/", BackendUserView.as_view(), name="registerStaff"),
    path("registerStaff/<str:id>/", UpdateStaffView.as_view(), name="updateStaff"),
    path("api/profile/update/", UpdateProfileView.as_view(), name="update_profile"),
    path(
        "change-password/",
        ChangePasswordView.as_view({"get": "list"}),
        name="change_password",
    ),
    path("staff-list/", GetAllStaff.as_view(), name="staff-list"),
    path("customers-list/", GetAllCustomer.as_view(), name="customer-list"),
    path("my-profile/<uuid:id>/", views.getUserInfo, name="user-profile"),
    path("update-myprofile/", UpdateMyProfile.as_view(), name="profile-update"),
    path(
        "update-customer-profile/<uuid:id>/",
        UpdateCustomerProfile.as_view(),
        name="customer-profile",
    ),
    path(
        "password-reset/request/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path("password-reset/", PasswordResetView.as_view(), name="password_reset"),
    path(
        "assign-permission/",
        CreateAdminPermissionView.as_view(),
        name="assign-permission",
    ),
    path("update-permission/<uuid:user_id>/", UpdatePermissionView.as_view()),
    path("getUserPermission/<str:id>/", views.getUserPermission, name="get-permission"),
    path("sessions/active/", ActiveUserSessionsView.as_view(), name="active-sessions"),
    path("sessions/<str:id>/terminate/", TerminateSessionView.as_view()),
    path(
        "users/reset-password/",
        ResetUserPasswordView.as_view({"get": "list"}),
        name="reset-user-password",
    ),
    # urls.py
    path(
        "notifications/config/",
        NotificationConfigView.as_view(),
        name="notification-config",
    ),
    path(
        "notifications/logs/",
        NotificationLogListView.as_view(),
        name="notification-log-list",
    ),
    # path("audit-log/",audit_report,name="audit-log")
]
