from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CodLedgerView, PaymentViewSet, SettlementViewSet

router = DefaultRouter()
router.register("settlements", SettlementViewSet, basename="settlement")
router.register("", PaymentViewSet, basename="payment")

urlpatterns = [
    path("cod-ledger/", CodLedgerView.as_view(), name="cod-ledger"),
    path("", include(router.urls)),
]
