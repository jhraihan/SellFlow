from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import (
    Cap,
    HasStoreCapability,
    IsStoreMember,
    IsStoreOwner,
)

from .adapters.base import CourierError
from .adapters.registry import build_adapter
from .models import Courier, StoreCourier
from .serializers import (
    CourierSerializer,
    StoreCourierSerializer,
    StoreCourierWriteSerializer,
)


@extend_schema(tags=["couriers"])
class CourierViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourierSerializer
    permission_classes = [IsAuthenticated]
    queryset = Courier.objects.filter(is_active=True)
    pagination_class = None


@extend_schema(tags=["couriers"])
class StoreCourierViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = StoreCourier.objects.all()
    capability_map = {
        "GET": Cap.VIEW_ORDERS,
        "POST": Cap.MANAGE_COURIER_CREDENTIALS,
        "PUT": Cap.MANAGE_COURIER_CREDENTIALS,
        "PATCH": Cap.MANAGE_COURIER_CREDENTIALS,
        "DELETE": Cap.MANAGE_COURIER_CREDENTIALS,
    }
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().select_related("courier")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return StoreCourierWriteSerializer
        return StoreCourierSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(store=request.store)
        return Response(
            StoreCourierSerializer(instance).data,
            status=http_status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(StoreCourierSerializer(instance).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="verify",
        permission_classes=[IsAuthenticated, IsStoreMember, IsStoreOwner],
    )
    def verify(self, request, pk=None):
        store_courier = self.get_object()
        adapter = build_adapter(store_courier)

        try:
            adapter.validate_credentials()
        except CourierError as exc:
            store_courier.last_error = exc.message[:300]
            store_courier.save(update_fields=["last_error", "updated_at"])
            return Response(
                {"verified": False, "message": exc.message,
                 "code": exc.code},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        except NotImplementedError:
            return Response({
                "verified": True,
                "message": (
                    f"{store_courier.courier.name} is used manually and needs "
                    "no credentials."
                ),
            })

        store_courier.last_verified_at = timezone.now()
        store_courier.last_error = ""
        store_courier.save(
            update_fields=["last_verified_at", "last_error", "updated_at"]
        )
        return Response({
            "verified": True,
            "message": f"{store_courier.courier.name} credentials are working.",
        })
