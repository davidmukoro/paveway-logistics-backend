from django.urls import path

from rest_framework.routers import DefaultRouter


from .views import TicketViewSet, TicketDetailViewSet

router = DefaultRouter()

router.register(r"crm-tickets", TicketViewSet, basename="crm-tickets")
router.register(
    r"crm-ticket-details", TicketDetailViewSet, basename="crm-ticket-details"
)

urlpatterns = router.urls + []
