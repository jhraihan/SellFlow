from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Plan
from .serializers import ActivatePlanSerializer, PlanSerializer
from .services import activate_plan, usage_summary


@extend_schema(tags=["billing"])
class PlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]
    queryset = Plan.objects.filter(is_active=True)
    pagination_class = None


@extend_schema(tags=["billing"])
class SubscriptionView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.VIEW_ORDERS

    def get(self, request):
        summary = usage_summary(request.store)
        if summary is None:
            return Response({"detail": "No plans are configured."})
        return Response(summary)


@extend_schema(tags=["billing"])
class ActivatePlanView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_BILLING

    def post(self, request):
        serializer = ActivatePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subscription = activate_plan(
            request.store,
            serializer.context["plan_obj"],
            actor=request.user,
            reference=serializer.validated_data.get("reference", ""),
            note=serializer.validated_data.get("note", ""),
        )
        return Response(usage_summary(subscription.store))
