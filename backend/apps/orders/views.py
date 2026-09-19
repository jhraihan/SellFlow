from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import APIError
from apps.core.mixins import StoreScopedMixin
from apps.core.pagination import HighVolumeCursorPagination
from apps.customers.models import Customer
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Order
from .serializers import (
    BulkStatusSerializer,
    CallLogSerializer,
    DuplicateCheckSerializer,
    ItemsUpdateSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderStatusHistorySerializer,
    OrderUpdateSerializer,
    StatusChangeSerializer,
)
from .services import (
    create_order,
    find_duplicate_orders,
    log_call,
    transition_status,
    update_items,
)


@extend_schema(tags=["orders"])
class OrderViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Order.objects.all()
    capability_map = {
        "GET": Cap.VIEW_ORDERS,
        "POST": Cap.MANAGE_ORDERS,
        "PUT": Cap.MANAGE_ORDERS,
        "PATCH": Cap.MANAGE_ORDERS,
        "DELETE": Cap.MANAGE_ORDERS,
    }
    pagination_class = HighVolumeCursorPagination
    filterset_fields = [
        "status", "source", "payment_status", "shipping_district", "customer",
    ]
    ordering_fields = ["created_at", "total_amount"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("customer", "created_by")
            .prefetch_related("items")
        )

        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(recipient_phone__icontains=search)
            )

        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        created_by = params.get("created_by")
        if created_by:
            queryset = queryset.filter(created_by_id=created_by)

        if params.get("open") == "true":
            queryset = queryset.open()

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrderUpdateSerializer
        if self.action == "retrieve":
            return OrderDetailSerializer
        return OrderListSerializer

    def _detail_response(self, order, status_code=http_status.HTTP_200_OK):
        order = (
            Order.objects.select_related("customer", "created_by")
            .prefetch_related("items", "status_history")
            .get(pk=order.pk)
        )
        return Response(
            OrderDetailSerializer(
                order, context=self.get_serializer_context()
            ).data,
            status=status_code,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = data["customer"]
        product_ids = [row["product"].id for row in data["items"]]

        if not data.get("acknowledge_duplicate"):
            duplicates = find_duplicate_orders(
                request.store, customer, product_ids
            )
            if duplicates:
                return Response(
                    {"error": {
                        "code": "POSSIBLE_DUPLICATE",
                        "message": (
                            "This customer already has a recent open order "
                            "with one of these products."
                        ),
                        "details": {
                            "orders": [
                                {
                                    "id": o.id,
                                    "order_number": o.order_number,
                                    "status": o.status,
                                    "created_at": o.created_at.isoformat(),
                                }
                                for o in duplicates
                            ]
                        },
                    }},
                    status=http_status.HTTP_409_CONFLICT,
                )

        order = create_order(
            request.store,
            customer=customer,
            items=data["items"],
            shipping=data["shipping"],
            source=data.get("source"),
            discount_amount=data.get("discount_amount", 0),
            delivery_charge=data.get("delivery_charge"),
            advance_paid=data.get("advance_paid", 0),
            internal_note=data.get("internal_note", ""),
            customer_note=data.get("customer_note", ""),
            actor=request.user,
        )
        return self._detail_response(order, http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = OrderUpdateSerializer(
            order, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self._detail_response(order)

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, pk=None):
        order = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = transition_status(
            order,
            data["status"],
            actor=request.user,
            note=data.get("note", ""),
            reason=data.get("reason", ""),
            cancel_note=data.get("cancel_note", ""),
        )
        return self._detail_response(order)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        order = self.get_object()
        serializer = CallLogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = log_call(
            order,
            serializer.validated_data["outcome"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return self._detail_response(order)

    @action(detail=True, methods=["patch"], url_path="items")
    def change_items(self, request, pk=None):
        order = self.get_object()
        serializer = ItemsUpdateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)

        order = update_items(
            order, serializer.validated_data["items"], actor=request.user
        )
        return self._detail_response(order)

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        order = self.get_object()
        return Response(
            OrderStatusHistorySerializer(
                order.status_history.select_related("actor"), many=True
            ).data
        )

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        queryset = self.get_queryset()
        counts = {}
        for row in queryset.values("status").annotate(n=Count("id")):
            counts[row["status"]] = row["n"]
        return Response({
            "by_status": counts,
            "total": sum(counts.values()),
        })


@extend_schema(tags=["orders"])
class BulkStatusView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_ORDERS

    def post(self, request):
        serializer = BulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        orders = self.scoped(Order.objects.all()).filter(
            pk__in=data["order_ids"]
        )
        found = {o.pk: o for o in orders}

        succeeded, failed = [], []
        for order_id in data["order_ids"]:
            order = found.get(order_id)
            if order is None:
                failed.append({
                    "id": order_id,
                    "code": "NOT_FOUND",
                    "message": "Order not found in this store.",
                })
                continue
            try:
                transition_status(
                    order,
                    data["status"],
                    actor=request.user,
                    note=data.get("note", ""),
                    reason=data.get("reason", ""),
                )
                succeeded.append(order_id)
            except APIError as exc:
                failed.append({
                    "id": order_id,
                    "code": exc.code,
                    "message": exc.message,
                })

        return Response({
            "succeeded": succeeded,
            "failed": failed,
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
        })


@extend_schema(tags=["orders"])
class DuplicateCheckView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.VIEW_ORDERS

    def post(self, request):
        serializer = DuplicateCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = (
            self.scoped(Customer.objects.all())
            .by_phone(data["phone"])
            .first()
        )
        if customer is None:
            return Response({"duplicates": []})

        matches = find_duplicate_orders(
            request.store, customer, data.get("product_ids", [])
        )
        return Response({
            "duplicates": [
                {
                    "id": o.id,
                    "order_number": o.order_number,
                    "status": o.status,
                    "total_amount": str(o.total_amount),
                    "created_at": o.created_at.isoformat(),
                }
                for o in matches
            ]
        })
