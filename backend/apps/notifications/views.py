from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Notification
from .serializers import MarkReadSerializer, NotificationSerializer


@extend_schema(tags=["notifications"])
class NotificationViewSet(StoreScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Notification.objects.all()
    required_capability = Cap.VIEW_ORDERS
    filterset_fields = ["notification_type", "level", "is_read"]

    def get_queryset(self):
        queryset = super().get_queryset().for_user(self.request.user)
        if self.request.query_params.get("unread") == "true":
            queryset = queryset.unread()
        return queryset

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": self.get_queryset().unread().count()})

    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        queryset = self.get_queryset().unread()
        if not data.get("all"):
            queryset = queryset.filter(pk__in=data["ids"])

        updated = queryset.update(is_read=True, read_at=timezone.now())
        return Response({"marked_read": updated})
