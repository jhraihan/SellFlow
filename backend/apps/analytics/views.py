import csv
from decimal import Decimal

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .services import (
    courier_performance,
    dashboard,
    district_performance,
    product_performance,
    profit_report,
    reconciliation_health,
    sales_series,
    staff_performance,
)


def as_money(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, dict):
        return {k: as_money(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_money(v) for v in value]
    return value


class AnalyticsView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.VIEW_ANALYTICS

    def params(self, request):
        return {
            "date_from": request.query_params.get("date_from"),
            "date_to": request.query_params.get("date_to"),
        }


@extend_schema(tags=["analytics"])
class DashboardView(AnalyticsView):
    def get(self, request):
        return Response(as_money(dashboard(request.store)))


@extend_schema(tags=["analytics"])
class SalesReportView(AnalyticsView):
    def get(self, request):
        group_by = request.query_params.get("group_by", "day")
        if group_by not in ("day", "week", "month"):
            group_by = "day"

        profit = profit_report(request.store, **self.params(request))
        series = sales_series(
            request.store, group_by=group_by, **self.params(request)
        )
        return Response(as_money({
            "summary": profit,
            "series": series["series"],
            "group_by": group_by,
            "period": profit["period"],
        }))


@extend_schema(tags=["analytics"])
class ProfitReportView(AnalyticsView):
    def get(self, request):
        return Response(
            as_money(profit_report(request.store, **self.params(request)))
        )


@extend_schema(tags=["analytics"])
class ProductReportView(AnalyticsView):
    def get(self, request):
        return Response(
            as_money(product_performance(request.store, **self.params(request)))
        )


@extend_schema(tags=["analytics"])
class CourierReportView(AnalyticsView):
    def get(self, request):
        return Response(
            as_money(courier_performance(request.store, **self.params(request)))
        )


@extend_schema(tags=["analytics"])
class DistrictReportView(AnalyticsView):
    def get(self, request):
        return Response(
            as_money(district_performance(request.store, **self.params(request)))
        )


@extend_schema(tags=["analytics"])
class StaffReportView(AnalyticsView):
    def get(self, request):
        return Response(
            as_money(staff_performance(request.store, **self.params(request)))
        )


@extend_schema(tags=["analytics"])
class ReconciliationHealthView(AnalyticsView):
    def get(self, request):
        return Response(as_money(reconciliation_health(request.store)))


EXPORTS = {
    "products": (product_performance, "products"),
    "couriers": (courier_performance, "couriers"),
    "districts": (district_performance, "districts"),
    "staff": (staff_performance, "staff"),
}


@extend_schema(tags=["analytics"])
class ExportView(AnalyticsView):
    def get(self, request):
        report = request.query_params.get("report", "products")
        if report not in EXPORTS:
            return Response(
                {"error": {
                    "code": "UNKNOWN_REPORT",
                    "message": f"Unknown report '{report}'.",
                    "details": {"available": sorted(EXPORTS)},
                }},
                status=400,
            )

        builder, key = EXPORTS[report]
        data = builder(request.store, **self.params(request))
        rows = data[key]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{report}-report.csv"'
        )

        if not rows:
            return response

        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return response
