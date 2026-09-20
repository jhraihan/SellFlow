from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Expense
from .serializers import ExpenseSerializer


@extend_schema(tags=["expenses"])
class ExpenseViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    required_capability = Cap.MANAGE_EXPENSES
    filterset_fields = ["category"]
    ordering_fields = ["date", "amount"]
    ordering = ["-date"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("created_by")
        params = self.request.query_params
        return queryset.in_period(
            params.get("date_from"), params.get("date_to")
        )

    def perform_create(self, serializer):
        serializer.save(store=self.request.store, created_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        queryset = self.get_queryset()
        by_category = list(
            queryset.values("category")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        total = queryset.aggregate(total=Sum("amount"))["total"] or 0
        return Response({"total": total, "by_category": by_category})
