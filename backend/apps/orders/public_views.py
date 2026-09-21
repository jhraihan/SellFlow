from decimal import Decimal

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import normalise_bd_phone
from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer
from apps.notifications.services import notify_public_order
from apps.stores.models import Store

from .models import OrderSource
from .services import create_order


class PublicOrderItemSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    variant = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class PublicOrderSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    district = serializers.CharField(max_length=60)
    thana = serializers.CharField(
        max_length=60, required=False, allow_blank=True
    )
    address_line = serializers.CharField(max_length=255)
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    items = PublicOrderItemSerializer(many=True)

    def validate_phone(self, value):
        from django.core.exceptions import ValidationError

        try:
            return normalise_bd_phone(value)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from None

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one item.")
        if len(value) > 20:
            raise serializers.ValidationError("Too many items in one order.")
        return value

    def validate(self, attrs):
        store = self.context["store"]
        resolved = []

        for row in attrs["items"]:
            product = Product.objects.filter(
                pk=row["product"], store=store, is_active=True
            ).first()
            if product is None:
                raise serializers.ValidationError(
                    {"items": "That product is not available."}
                )

            variant = None
            if row.get("variant"):
                variant = ProductVariant.objects.filter(
                    pk=row["variant"], product=product, is_active=True
                ).first()
                if variant is None:
                    raise serializers.ValidationError(
                        {"items": "That option is not available."}
                    )
            elif product.has_variants:
                raise serializers.ValidationError(
                    {"items": f"Choose an option for {product.name}."}
                )

            resolved.append({
                "product": product,
                "variant": variant,
                "quantity": row["quantity"],
            })

        attrs["resolved_items"] = resolved
        return attrs


@extend_schema(tags=["public"])
class PublicStoreView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_track"

    def get(self, request, slug):
        store = Store.objects.filter(
            slug=slug, is_active=True
        ).select_related("settings").first()
        if store is None:
            return Response(status=http_status.HTTP_404_NOT_FOUND)

        products = (
            Product.objects.filter(store=store, is_active=True)
            .prefetch_related("variants")
            .order_by("name")[:200]
        )

        return Response({
            "store": {
                "name": store.name,
                "slug": store.slug,
                "district": store.district,
                "contact_phone": store.contact_phone,
            },
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "price": str(product.selling_price),
                    "has_variants": product.has_variants,
                    "variants": [
                        {
                            "id": variant.id,
                            "label": variant.label,
                            "price": str(variant.selling_price),
                        }
                        for variant in product.variants.all()
                        if variant.is_active
                    ],
                }
                for product in products
            ],
        })


@extend_schema(tags=["public"])
class PublicOrderCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_order"

    def post(self, request, slug):
        store = Store.objects.filter(
            slug=slug, is_active=True
        ).select_related("settings").first()
        if store is None:
            return Response(status=http_status.HTTP_404_NOT_FOUND)

        serializer = PublicOrderSerializer(
            data=request.data, context={"store": store}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = Customer.objects.filter(
            store=store, phone=data["phone"]
        ).first()
        if customer is None:
            customer = Customer.objects.create(
                store=store, name=data["name"], phone=data["phone"]
            )

        if customer.is_blacklisted:
            return Response(
                {
                    "detail": (
                        "We could not place this order. Please contact the "
                        "shop directly."
                    )
                },
                status=http_status.HTTP_403_FORBIDDEN,
            )

        order = create_order(
            store,
            customer=customer,
            items=data["resolved_items"],
            shipping={
                "recipient_name": data["name"],
                "recipient_phone": data["phone"],
                "district": data["district"],
                "thana": data.get("thana", ""),
                "address_line": data["address_line"],
            },
            source=OrderSource.PUBLIC_FORM,
            customer_note=data.get("note", ""),
            advance_paid=Decimal("0.00"),
        )

        notify_public_order(order)

        return Response(
            {
                "order_number": order.order_number,
                "total_amount": str(order.total_amount),
                "cod_amount": str(order.cod_amount),
                "delivery_charge": str(order.delivery_charge),
                "message": (
                    "Thank you. The shop will call you to confirm this order."
                ),
            },
            status=http_status.HTTP_201_CREATED,
        )
