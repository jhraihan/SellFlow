from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ReturnAnalyticsView, ReturnViewSet

router = DefaultRouter()
router.register("", ReturnViewSet, basename="return")

urlpatterns = [
    path("analytics/", ReturnAnalyticsView.as_view(), name="return-analytics"),
    path("", include(router.urls)),
]
