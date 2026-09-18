from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ProductExportView,
    ProductImportView,
    ProductViewSet,
    StockAdjustView,
    StockMovementViewSet,
    StockReceiveView,
    StockViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("stock/movements", StockMovementViewSet, basename="stock-movement")
router.register("stock", StockViewSet, basename="stock")

urlpatterns = [
    path("products/export/", ProductExportView.as_view(), name="product-export"),
    path("products/import/", ProductImportView.as_view(), name="product-import"),
    path("stock/adjust/", StockAdjustView.as_view(), name="stock-adjust"),
    path("stock/receive/", StockReceiveView.as_view(), name="stock-receive"),
    path("", include(router.urls)),
]
