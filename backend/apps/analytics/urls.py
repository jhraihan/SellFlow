from django.urls import path

from .views import (
    CourierReportView,
    DashboardView,
    DistrictReportView,
    ExportView,
    ProductReportView,
    ProfitReportView,
    ReconciliationHealthView,
    SalesReportView,
    StaffReportView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="analytics-dashboard"),
    path("sales/", SalesReportView.as_view(), name="analytics-sales"),
    path("profit/", ProfitReportView.as_view(), name="analytics-profit"),
    path("products/", ProductReportView.as_view(), name="analytics-products"),
    path("couriers/", CourierReportView.as_view(), name="analytics-couriers"),
    path("districts/", DistrictReportView.as_view(), name="analytics-districts"),
    path("staff/", StaffReportView.as_view(), name="analytics-staff"),
    path(
        "reconciliation/",
        ReconciliationHealthView.as_view(),
        name="analytics-reconciliation",
    ),
    path("export/", ExportView.as_view(), name="analytics-export"),
]
