from django.contrib import admin
from django.urls import path, include
from setup.views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    ProtectedEndpointView,
    LogoutView,
    validate_token,
)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/setup/", include("setup.urls")),
    path("api/orders/", include("logistics.urls")),
    path("api/finance/", include("finance.urls")),
    path("api/hcms/", include("hmcs.urls")),
    path("api/token/", CustomTokenObtainPairView.as_view(), name="get_token"),
    path("api/token/refresh/", CustomTokenRefreshView.as_view(), name="refresh"),
    path(
        "api/protected-endpoint/",
        ProtectedEndpointView.as_view(),
        name="protected-endpoint",
    ),
    path(
        "api/token/logout/", LogoutView.as_view(), name="logout"
    ),  # Add logout endpoint
    path(
        "api/validate-token/", view=validate_token, name="validate-token"
    ),  # Add validate token endpoint
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
