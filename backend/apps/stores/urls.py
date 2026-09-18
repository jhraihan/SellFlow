from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    InvitationViewSet,
    MyCapabilitiesView,
    StaffViewSet,
    StoreViewSet,
)

router = DefaultRouter()
router.register("staff", StaffViewSet, basename="staff")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("", StoreViewSet, basename="store")

urlpatterns = [
    path(
        "invitations/accept/",
        AcceptInvitationView.as_view(),
        name="invitation-accept",
    ),
    path(
        "my-capabilities/",
        MyCapabilitiesView.as_view(),
        name="my-capabilities",
    ),
    path("", include(router.urls)),
]
