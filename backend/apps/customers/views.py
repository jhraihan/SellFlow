from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Customer, CustomerAddress
from .serializers import (
    BlacklistSerializer,
    CustomerAddressSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerLookupSerializer,
    CustomerWriteSerializer,
)


@extend_schema(tags=["customers"])
class CustomerViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Customer.objects.all()
    capability_map = {
        "GET": Cap.VIEW_CUSTOMERS,
        "POST": Cap.MANAGE_CUSTOMERS,
        "PUT": Cap.MANAGE_CUSTOMERS,
        "PATCH": Cap.MANAGE_CUSTOMERS,
        "DELETE": Cap.MANAGE_CUSTOMERS,
    }
    filterset_fields = ["risk_level", "is_blacklisted"]
    search_fields = ["name", "phone", "facebook_name"]
    ordering_fields = ["name", "created_at", "last_order_at", "lifetime_value"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("addresses")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CustomerWriteSerializer
        if self.action == "retrieve":
            return CustomerDetailSerializer
        return CustomerListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            CustomerDetailSerializer(
                customer, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            CustomerDetailSerializer(
                customer, context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["post"], url_path="blacklist")
    def blacklist(self, request, pk=None):
        customer = self.get_object()
        serializer = BlacklistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer.is_blacklisted = serializer.validated_data["is_blacklisted"]
        customer.blacklist_reason = serializer.validated_data.get("reason", "")
        if not customer.is_blacklisted:
            customer.risk_level = customer.compute_risk_level()
        customer.save()

        return Response(
            CustomerDetailSerializer(
                customer, context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["get", "post"], url_path="addresses")
    def addresses(self, request, pk=None):
        customer = self.get_object()

        if request.method == "GET":
            return Response(
                CustomerAddressSerializer(
                    customer.addresses.all(), many=True
                ).data
            )

        serializer = CustomerAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(store=request.store, customer=customer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["customers"])
class CustomerAddressViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    serializer_class = CustomerAddressSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = CustomerAddress.objects.all()
    capability_map = {
        "GET": Cap.VIEW_CUSTOMERS,
        "PUT": Cap.MANAGE_CUSTOMERS,
        "PATCH": Cap.MANAGE_CUSTOMERS,
        "DELETE": Cap.MANAGE_CUSTOMERS,
    }
    http_method_names = ["get", "patch", "delete", "head", "options"]


@extend_schema(tags=["customers"])
class CustomerLookupView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.VIEW_CUSTOMERS

    def get(self, request):
        phone = request.query_params.get("phone", "").strip()
        if not phone:
            return Response(
                {"error": {
                    "code": "VALIDATION_ERROR",
                    "message": "A phone number is required.",
                    "details": {"phone": ["This query parameter is required."]},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = (
            self.scoped(Customer.objects.all())
            .by_phone(phone)
            .prefetch_related("addresses")
            .first()
        )
        if customer is None:
            return Response({"found": False, "customer": None})

        return Response({
            "found": True,
            "customer": CustomerLookupSerializer(customer).data,
        })
