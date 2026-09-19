import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import APIError
from apps.core.mixins import StoreScopedMixin
from apps.couriers.adapters.base import TrackingEvent
from apps.couriers.adapters.registry import build_adapter
from apps.couriers.models import Courier, StoreCourier
from apps.orders.models import Order
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Shipment
from .serializers import (
    BookShipmentSerializer,
    BulkBookSerializer,
    ManualStatusSerializer,
    ShipmentCostSerializer,
    ShipmentDetailSerializer,
    ShipmentListSerializer,
)
from .services import (
    ShipmentError,
    book_shipment,
    cancel_shipment,
    record_tracking_events,
    sync_shipment,
)

logger = logging.getLogger(__name__)


@extend_schema(tags=["shipments"])
class ShipmentViewSet(StoreScopedMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Shipment.objects.all()
    required_capability = Cap.VIEW_ORDERS
    filterset_fields = ["cod_status", "booking_mode", "store_courier"]
    ordering_fields = ["created_at", "booked_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related(
                "order__customer", "store_courier__courier", "booked_by"
            )
        )
        params = self.request.query_params

        if params.get("in_transit") == "true":
            queryset = queryset.in_transit()
        if params.get("cod_outstanding") == "true":
            queryset = queryset.cod_outstanding()

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(consignment_id__icontains=search)

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ShipmentDetailSerializer
        return ShipmentListSerializer

    def _detail(self, shipment):
        shipment = (
            Shipment.objects.select_related(
                "order__customer", "store_courier__courier", "booked_by"
            )
            .prefetch_related("tracking_history")
            .get(pk=shipment.pk)
        )
        return Response(ShipmentDetailSerializer(shipment).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="sync",
        permission_classes=[IsAuthenticated, IsStoreMember, HasStoreCapability],
    )
    def sync(self, request, pk=None):
        shipment = self.get_object()
        shipment = sync_shipment(shipment, actor=request.user)
        return self._detail(shipment)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        shipment = self.get_object()
        shipment = cancel_shipment(shipment, actor=request.user)
        return self._detail(shipment)

    @action(detail=True, methods=["post"], url_path="status")
    def manual_status(self, request, pk=None):
        shipment = self.get_object()
        serializer = ManualStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        adapter = build_adapter(shipment.store_courier)
        event = TrackingEvent(
            raw_status=data["raw_status"],
            mapped_status=adapter.map_status(data["raw_status"]),
            note=data.get("note", ""),
            location=data.get("location", ""),
            observed_at=timezone.now(),
        )
        shipment = record_tracking_events(
            shipment, [event], source="manual", actor=request.user
        )
        return self._detail(shipment)

    @action(detail=True, methods=["post"], url_path="cost")
    def set_cost(self, request, pk=None):
        shipment = self.get_object()
        serializer = ShipmentCostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shipment.actual_cost = serializer.validated_data["actual_cost"]
        shipment.save(update_fields=["actual_cost", "updated_at"])
        return self._detail(shipment)


@extend_schema(tags=["shipments"])
class BookShipmentView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.BOOK_SHIPMENTS

    def post(self, request):
        serializer = BookShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = self.scoped(Order.objects.all()).filter(
            pk=data["order"]
        ).first()
        if order is None:
            raise ShipmentError(
                "Unknown order.", code="ORDER_NOT_FOUND",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        store_courier = self.scoped(StoreCourier.objects.all()).filter(
            pk=data["store_courier"]
        ).select_related("courier").first()
        if store_courier is None:
            raise ShipmentError(
                "Unknown courier for this store.",
                code="COURIER_NOT_FOUND",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        shipment = book_shipment(
            order,
            store_courier,
            actor=request.user,
            manual_consignment_id=data.get("consignment_id", ""),
        )

        shipment = (
            Shipment.objects.select_related(
                "order__customer", "store_courier__courier", "booked_by"
            )
            .prefetch_related("tracking_history")
            .get(pk=shipment.pk)
        )
        return Response(
            ShipmentDetailSerializer(shipment).data,
            status=http_status.HTTP_201_CREATED,
        )


@extend_schema(tags=["shipments"])
class BulkBookView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.BOOK_SHIPMENTS

    def post(self, request):
        serializer = BulkBookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        store_courier = self.scoped(StoreCourier.objects.all()).filter(
            pk=data["store_courier"]
        ).select_related("courier").first()
        if store_courier is None:
            raise ShipmentError(
                "Unknown courier for this store.",
                code="COURIER_NOT_FOUND",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        orders = {
            o.pk: o
            for o in self.scoped(Order.objects.all()).filter(
                pk__in=data["order_ids"]
            )
        }

        succeeded, failed = [], []
        for order_id in data["order_ids"]:
            order = orders.get(order_id)
            if order is None:
                failed.append({
                    "order_id": order_id,
                    "code": "ORDER_NOT_FOUND",
                    "message": "Order not found in this store.",
                })
                continue
            try:
                shipment = book_shipment(
                    order, store_courier, actor=request.user
                )
                succeeded.append({
                    "order_id": order_id,
                    "order_number": order.order_number,
                    "consignment_id": shipment.consignment_id,
                })
            except APIError as exc:
                failed.append({
                    "order_id": order_id,
                    "order_number": order.order_number,
                    "code": exc.code,
                    "message": exc.message,
                })

        return Response({
            "succeeded": succeeded,
            "failed": failed,
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
        })


@extend_schema(tags=["shipments"])
class CourierWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_track"

    def post(self, request, courier_code):
        courier = Courier.objects.filter(
            code=courier_code, is_active=True
        ).first()
        if courier is None:
            return Response(status=http_status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        consignment_id = str(
            payload.get("consignment_id")
            or payload.get("merchant_order_id")
            or payload.get("invoice")
            or ""
        ).strip()

        if not consignment_id:
            return Response(
                {"detail": "No consignment id in payload."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        shipment = (
            Shipment.objects.select_related("store_courier__courier", "order")
            .filter(
                consignment_id=consignment_id,
                store_courier__courier=courier,
            )
            .first()
        )
        if shipment is None:
            logger.info(
                "Webhook for unknown consignment %s from %s",
                consignment_id, courier_code,
            )
            return Response(status=http_status.HTTP_202_ACCEPTED)

        adapter = build_adapter(shipment.store_courier)

        if not adapter.verify_webhook(payload, request.META):
            logger.warning(
                "Rejected unverified webhook for %s from %s",
                consignment_id, courier_code,
            )
            return Response(
                {"detail": "Signature verification failed."},
                status=http_status.HTTP_401_UNAUTHORIZED,
            )

        try:
            events = adapter.parse_webhook(payload, request.META)
        except NotImplementedError:
            return Response(status=http_status.HTTP_202_ACCEPTED)

        record_tracking_events(shipment, events, source="webhook")
        return Response(status=http_status.HTTP_202_ACCEPTED)
