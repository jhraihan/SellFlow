from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Return
from .serializers import (
    ResolveReturnSerializer,
    ReturnCreateSerializer,
    ReturnDetailSerializer,
    ReturnListSerializer,
)
from .services import (
    create_return,
    receive_return,
    resolve_return,
    return_analytics,
)


@extend_schema(tags=["returns"])
class ReturnViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Return.objects.all()
    capability_map = {
        "GET": Cap.VIEW_ORDERS,
        "POST": Cap.RECORD_RETURNS,
        "PATCH": Cap.RECORD_RETURNS,
        "DELETE": Cap.RECORD_RETURNS,
    }
    filterset_fields = ["status", "reason", "return_type"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("order__customer", "shipment", "created_by")
            .prefetch_related("items__order_item")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ReturnDetailSerializer
        return ReturnListSerializer

    def _detail(self, record, status_code=http_status.HTTP_200_OK):
        record = (
            Return.objects.select_related(
                "order__customer", "shipment", "created_by"
            )
            .prefetch_related("items__order_item")
            .get(pk=record.pk)
        )
        return Response(
            ReturnDetailSerializer(record).data, status=status_code
        )

    def create(self, request, *args, **kwargs):
        serializer = ReturnCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = serializer.context["order_obj"]
        items = None
        if data.get("items"):
            items = [
                {
                    "order_item": row["order_item"],
                    "quantity": row["quantity"],
                    "condition": row["condition"],
                    "note": row.get("note", ""),
                }
                for row in data["items"]
            ]

        record = create_return(
            request.store,
            order,
            reason=data["reason"],
            reason_note=data.get("reason_note", ""),
            return_type=data.get("return_type"),
            items=items,
            return_charge=data.get("return_charge", 0),
            actor=request.user,
        )
        return self._detail(record, http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        record = self.get_object()
        record = receive_return(record, actor=request.user)
        return self._detail(record)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        record = self.get_object()
        serializer = ResolveReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        kwargs = {
            "item_dispositions": data.get("item_dispositions"),
            "refund_amount": data.get("refund_amount"),
            "resolution_note": data.get("resolution_note", ""),
            "actor": request.user,
        }
        if data.get("refund_method"):
            kwargs["refund_method"] = data["refund_method"]

        record = resolve_return(record, **kwargs)
        return self._detail(record)


@extend_schema(tags=["returns"])
class ReturnAnalyticsView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.VIEW_ANALYTICS

    def get(self, request):
        data = return_analytics(
            request.store,
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
        )
        return Response(data)
