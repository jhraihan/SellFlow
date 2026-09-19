from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BulkStatusView, DuplicateCheckView, OrderViewSet

router = DefaultRouter()
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("bulk-status/", BulkStatusView.as_view(), name="order-bulk-status"),
    path(
        "check-duplicate/",
        DuplicateCheckView.as_view(),
        name="order-check-duplicate",
    ),
    path("", include(router.urls)),
]
