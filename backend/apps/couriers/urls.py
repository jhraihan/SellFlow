from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CourierViewSet, StoreCourierViewSet

router = DefaultRouter()
router.register("store-couriers", StoreCourierViewSet, basename="store-courier")
router.register("", CourierViewSet, basename="courier")

urlpatterns = [path("", include(router.urls))]
