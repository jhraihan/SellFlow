from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerAddressViewSet, CustomerLookupView, CustomerViewSet

router = DefaultRouter()
router.register("addresses", CustomerAddressViewSet, basename="customer-address")
router.register("", CustomerViewSet, basename="customer")

urlpatterns = [
    path("lookup/", CustomerLookupView.as_view(), name="customer-lookup"),
    path("", include(router.urls)),
]
