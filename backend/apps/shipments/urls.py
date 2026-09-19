from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BookShipmentView, BulkBookView, ShipmentViewSet

router = DefaultRouter()
router.register("", ShipmentViewSet, basename="shipment")

urlpatterns = [
    path("book/", BookShipmentView.as_view(), name="shipment-book"),
    path("bulk-book/", BulkBookView.as_view(), name="shipment-bulk-book"),
    path("", include(router.urls)),
]
