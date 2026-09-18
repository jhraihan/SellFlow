import csv
import io
from decimal import Decimal, InvalidOperation

from django.db.models import F, Sum
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import StoreScopedMixin
from apps.stores.permissions import Cap, HasStoreCapability, IsStoreMember

from .models import Category, Product, ProductImage, StockItem, StockMovement
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
    StockAdjustSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    StockReceiveSerializer,
)
from .services import adjust_stock, receive_stock


@extend_schema(tags=["catalog"])
class CategoryViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Category.objects.all()
    capability_map = {
        "GET": Cap.VIEW_PRODUCTS,
        "POST": Cap.MANAGE_PRODUCTS,
        "PUT": Cap.MANAGE_PRODUCTS,
        "PATCH": Cap.MANAGE_PRODUCTS,
        "DELETE": Cap.MANAGE_PRODUCTS,
    }
    pagination_class = None


@extend_schema(tags=["catalog"])
class ProductViewSet(StoreScopedMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = Product.objects.all()
    capability_map = {
        "GET": Cap.VIEW_PRODUCTS,
        "POST": Cap.MANAGE_PRODUCTS,
        "PUT": Cap.MANAGE_PRODUCTS,
        "PATCH": Cap.MANAGE_PRODUCTS,
        "DELETE": Cap.MANAGE_PRODUCTS,
    }
    filterset_fields = ["category", "is_active", "has_variants"]
    search_fields = ["name", "sku", "description"]
    ordering_fields = ["name", "selling_price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("category")
        queryset = queryset.prefetch_related(
            "images", "stock_items", "variants__stock_item"
        )
        if self.request.query_params.get("low_stock") == "true":
            queryset = queryset.filter(
                stock_items__on_hand__lte=F("low_stock_threshold")
            ).distinct()
        return queryset

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(
            ProductDetailSerializer(
                product, context=self.get_serializer_context()
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
        product = serializer.save()
        return Response(
            ProductDetailSerializer(
                product, context=self.get_serializer_context()
            ).data
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @action(detail=True, methods=["post"], url_path="images")
    def upload_image(self, request, pk=None):
        product = self.get_object()
        if product.images.count() >= ProductImage.MAX_PER_PRODUCT:
            return Response(
                {"error": {
                    "code": "IMAGE_LIMIT_REACHED",
                    "message": (
                        f"A product may have at most "
                        f"{ProductImage.MAX_PER_PRODUCT} images."
                    ),
                    "details": {},
                }},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = ProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_first = not product.images.exists()
        serializer.save(product=product, is_primary=is_first)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="movements")
    def movements(self, request, pk=None):
        product = self.get_object()
        queryset = StockMovement.objects.filter(
            stock_item__product=product
        ).select_related("stock_item__variant", "actor")
        page = self.paginate_queryset(queryset)
        serializer = StockMovementSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)


@extend_schema(tags=["stock"])
class StockViewSet(StoreScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockLevelSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = StockItem.objects.all()
    required_capability = Cap.VIEW_PRODUCTS

    def get_queryset(self):
        queryset = super().get_queryset().select_related("product", "variant")
        if self.request.query_params.get("low_stock") == "true":
            queryset = queryset.filter(
                on_hand__lte=F("product__low_stock_threshold")
            )
        return queryset.order_by("product__name")

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        queryset = self.get_queryset()
        totals = queryset.aggregate(
            on_hand=Sum("on_hand"), reserved=Sum("reserved")
        )
        on_hand = totals["on_hand"] or 0
        reserved = totals["reserved"] or 0
        low = sum(1 for item in queryset if item.is_low)
        return Response({
            "on_hand": on_hand,
            "reserved": reserved,
            "available": on_hand - reserved,
            "low_stock_count": low,
        })


@extend_schema(tags=["stock"])
class StockAdjustView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_PRODUCTS

    def post(self, request):
        serializer = StockAdjustSerializer(
            data=request.data,
            context={"store": request.store, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.context["item"]

        movement = adjust_stock(
            item,
            serializer.validated_data["new_on_hand"],
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        item.refresh_from_db()
        return Response({
            "stock": StockLevelSerializer(item).data,
            "movement": (
                StockMovementSerializer(movement).data if movement else None
            ),
        })


@extend_schema(tags=["stock"])
class StockReceiveView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_PRODUCTS

    def post(self, request):
        serializer = StockReceiveSerializer(
            data=request.data,
            context={"store": request.store, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.context["item"]

        movement = receive_stock(
            item,
            serializer.validated_data["quantity"],
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        item.refresh_from_db()
        return Response({
            "stock": StockLevelSerializer(item).data,
            "movement": StockMovementSerializer(movement).data,
        })


@extend_schema(tags=["stock"])
class StockMovementViewSet(StoreScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    queryset = StockMovement.objects.all()
    required_capability = Cap.VIEW_PRODUCTS
    filterset_fields = ["movement_type", "stock_item"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("stock_item__product", "stock_item__variant", "actor")
        )


CSV_COLUMNS = [
    "name", "sku", "category", "description",
    "selling_price", "cost_price", "weight_grams",
    "low_stock_threshold", "opening_stock",
]


@extend_schema(tags=["catalog"])
class ProductExportView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_PRODUCTS

    def get(self, request):
        from django.http import HttpResponse

        products = (
            self.scoped(Product.objects.all())
            .select_related("category")
            .prefetch_related("stock_items")
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'

        writer = csv.writer(response)
        writer.writerow(CSV_COLUMNS)
        for product in products:
            stock = sum(i.on_hand for i in product.stock_items.all())
            writer.writerow([
                product.name,
                product.sku,
                product.category.name if product.category else "",
                product.description,
                product.selling_price,
                product.cost_price,
                product.weight_grams,
                product.low_stock_threshold,
                stock,
            ])
        return response


@extend_schema(tags=["catalog"])
class ProductImportView(StoreScopedMixin, APIView):
    permission_classes = [IsAuthenticated, IsStoreMember, HasStoreCapability]
    required_capability = Cap.MANAGE_PRODUCTS

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Attach a CSV file.",
                    "details": {"file": ["This field is required."]},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        commit = str(request.data.get("commit", "false")).lower() == "true"

        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response(
                {"error": {
                    "code": "INVALID_ENCODING",
                    "message": "The file must be UTF-8 encoded CSV.",
                    "details": {},
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(text))
        valid, errors = self._validate_rows(reader, request.store)

        if not commit or errors:
            return Response({
                "dry_run": not commit,
                "valid_count": len(valid),
                "error_count": len(errors),
                "errors": errors[:50],
                "committed": False,
            })

        created = self._commit_rows(valid, request)
        return Response({
            "dry_run": False,
            "valid_count": len(valid),
            "error_count": 0,
            "errors": [],
            "committed": True,
            "created_count": created,
        })

    def _validate_rows(self, reader, store):
        valid, errors = [], []
        seen_skus = set()

        for line_no, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            if len(name) < 2:
                errors.append({"line": line_no, "field": "name",
                               "message": "Name is required."})
                continue

            try:
                selling = Decimal(str(row.get("selling_price") or "0"))
                cost = Decimal(str(row.get("cost_price") or "0"))
            except InvalidOperation:
                errors.append({"line": line_no, "field": "selling_price",
                               "message": "Prices must be numbers."})
                continue

            if selling < 0 or cost < 0:
                errors.append({"line": line_no, "field": "selling_price",
                               "message": "Prices cannot be negative."})
                continue

            sku = (row.get("sku") or "").strip().upper()
            if sku:
                if sku in seen_skus:
                    errors.append({"line": line_no, "field": "sku",
                                   "message": f"Duplicate SKU in file: {sku}."})
                    continue
                if Product.objects.filter(store=store, sku=sku).exists():
                    errors.append({"line": line_no, "field": "sku",
                                   "message": f"SKU already exists: {sku}."})
                    continue
                seen_skus.add(sku)

            valid.append({
                "line": line_no,
                "name": name,
                "sku": sku,
                "category": (row.get("category") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "selling_price": selling,
                "cost_price": cost,
                "weight_grams": int(row.get("weight_grams") or 0),
                "low_stock_threshold": int(row.get("low_stock_threshold") or 5),
                "opening_stock": int(row.get("opening_stock") or 0),
            })
        return valid, errors

    def _commit_rows(self, rows, request):
        from django.db import transaction

        from .services import get_or_create_stock_item

        store = request.store
        created = 0

        with transaction.atomic():
            for row in rows:
                category = None
                if row["category"]:
                    category, _ = Category.objects.get_or_create(
                        store=store, name=row["category"]
                    )
                product = Product.objects.create(
                    store=store,
                    name=row["name"],
                    sku=row["sku"],
                    category=category,
                    description=row["description"],
                    selling_price=row["selling_price"],
                    cost_price=row["cost_price"],
                    weight_grams=row["weight_grams"],
                    low_stock_threshold=row["low_stock_threshold"],
                )
                item = get_or_create_stock_item(product, None)
                if row["opening_stock"]:
                    receive_stock(
                        item,
                        row["opening_stock"],
                        actor=request.user,
                        reason="CSV import",
                    )
                created += 1
        return created
