from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActivatePlanView, PlanViewSet, SubscriptionView

router = DefaultRouter()
router.register("plans", PlanViewSet, basename="plan")

urlpatterns = [
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    path("activate/", ActivatePlanView.as_view(), name="activate-plan"),
    path("", include(router.urls)),
]
