from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.couriers.models import StoreCourier
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import CourierSettlement, Payment
from .serializers import (
    PaymentCreateSerializer,
    PaymentSerializer,
    SettlementCommitSerializer,
    SettlementDetailSerializer,
    SettlementSerializer,
    SettlementUploadSerializer,
)
from .services import (
    SettlementError,
    cod_ledger,
    commit_settlement,
    create_settlement_draft,
    discard_settlement,
    parse_settlement_csv,
    record_payment,
)


@extend_schema(tags=["payments"])
class PaymentViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    capability_map = {
        "GET": Cap.RECORD_PAYMENTS,
        "POST": Cap.RECORD_PAYMENTS,
        "PATCH": Cap.RECORD_PAYMENTS,
        "DELETE": Cap.RECORD_PAYMENTS,
    }
    filterset_fields = ["method", "direction", "order"]
    ordering_fields = ["received_at", "amount"]
    ordering = ["-received_at"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "order", "recorded_by"
        )
        params = self.request.query_params

        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(received_at__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(received_at__date__lte=date_to)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = PaymentCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = record_payment(
            request.store,
            amount=data["amount"],
            method=data["method"],
            order=serializer.context.get("order_obj"),
            direction=data["direction"],
            reference=data.get("reference", ""),
            note=data.get("note", ""),
            received_at=data.get("received_at"),
            actor=request.user,
        )
        return Response(
            PaymentSerializer(payment).data,
            status=http_status.HTTP_201_CREATED,
        )


@extend_schema(tags=["payments"])
class SettlementViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = CourierSettlement.objects.all()
    required_capability = Cap.RECONCILE_COD
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("store_courier__courier", "created_by")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SettlementDetailSerializer
        return SettlementSerializer

    def create(self, request, *args, **kwargs):
        serializer = SettlementUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        store_courier = self.scoped(StoreCourier.objects.all()).filter(
            pk=data["store_courier"]
        ).select_related("courier").first()
        if store_courier is None:
            raise SettlementError(
                "Unknown courier for this store.",
                code="COURIER_NOT_FOUND",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        upload = data["file"]
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SettlementError(
                "The statement must be a UTF-8 encoded CSV file.",
                code="INVALID_ENCODING",
            ) from None

        rows = parse_settlement_csv(text)
        upload.seek(0)

        settlement = create_settlement_draft(
            request.store,
            store_courier,
            rows,
            statement_reference=data.get("statement_reference", ""),
            original_filename=getattr(upload, "name", ""),
            uploaded_file=upload,
            actor=request.user,
        )
        if data.get("period_start") or data.get("period_end"):
            settlement.period_start = data.get("period_start")
            settlement.period_end = data.get("period_end")
            settlement.save(
                update_fields=["period_start", "period_end", "updated_at"]
            )

        settlement = CourierSettlement.objects.prefetch_related(
            "lines__shipment__order"
        ).get(pk=settlement.pk)
        return Response(
            SettlementDetailSerializer(settlement).data,
            status=http_status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        settlement = self.get_object()
        lines = settlement.lines.select_related("shipment__order")

        buckets = {"matched": [], "unmatched": [], "amount_mismatch": [],
                   "already_settled": []}
        from .serializers import SettlementLineSerializer

        for line in lines:
            buckets.setdefault(line.match_status, []).append(
                SettlementLineSerializer(line).data
            )

        return Response({
            "settlement": SettlementSerializer(settlement).data,
            "buckets": buckets,
            "counts": {k: len(v) for k, v in buckets.items()},
        })

    @action(detail=True, methods=["post"], url_path="commit")
    def commit(self, request, pk=None):
        settlement = self.get_object()
        serializer = SettlementCommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = commit_settlement(
            settlement,
            actor=request.user,
            include_mismatches=serializer.validated_data["include_mismatches"],
        )
        return Response({
            "settlement": SettlementSerializer(result["settlement"]).data,
            "settled_count": result["settled_count"],
        })

    def perform_destroy(self, instance):
        discard_settlement(instance)


@extend_schema(tags=["payments"])
class CodLedgerView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.RECONCILE_COD

    def get(self, request):
        overdue_days = request.query_params.get("overdue_days")
        ledger = cod_ledger(
            request.store,
            overdue_days=int(overdue_days) if overdue_days else None,
        )
        return Response(ledger)
