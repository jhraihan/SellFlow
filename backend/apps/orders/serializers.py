from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer
from apps.customers.serializers import CustomerLookupSerializer
from apps.stores.permissions import Cap, role_has

from .models import (
    CallOutcome,
    CancelReason,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    OrderStatusHistory,
)


class OrderItemSerializer(serializers.ModelSerializer):
    line_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    line_margin = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderItem
        fields = [
            "id", "product", "variant", "product_name", "variant_label",
            "sku", "unit_price", "unit_cost", "quantity", "line_total",
            "line_cost", "line_margin",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not _may_see_cost(self.context):
            data.pop("unit_cost", None)
            data.pop("line_cost", None)
            data.pop("line_margin", None)
        return data


def _may_see_cost(context):
    membership = context.get("membership")
    if membership is None:
        return False
    return role_has(membership.role, Cap.VIEW_COST_PRICE)


class OrderItemInputSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    variant = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )

    def validate(self, attrs):
        store = self.context["store"]

        product = Product.objects.filter(
            pk=attrs["product"], store=store
        ).first()
        if product is None:
            raise serializers.ValidationError(
                {"product": "Unknown product."}
            )
        attrs["product"] = product

        variant_id = attrs.get("variant")
        if variant_id:
            variant = ProductVariant.objects.filter(
                pk=variant_id, store=store, product=product
            ).first()
            if variant is None:
                raise serializers.ValidationError(
                    {"variant": "Unknown variant for this product."}
                )
            attrs["variant"] = variant
        else:
            attrs["variant"] = None
        return attrs


class ShippingSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    recipient_phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    district = serializers.CharField(max_length=60)
    thana = serializers.CharField(
        max_length=60, required=False, allow_blank=True
    )
    area = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    address_line = serializers.CharField(max_length=255)


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    to_status_display = serializers.CharField(
        source="get_to_status_display", read_only=True
    )

    class Meta:
        model = OrderStatusHistory
        fields = [
            "id", "from_status", "to_status", "to_status_display",
            "note", "actor_name", "created_at",
        ]
        read_only_fields = fields


class OrderListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(
        source="customer.phone", read_only=True
    )
    customer_risk = serializers.CharField(
        source="customer.risk_level", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "status_display", "source",
            "customer", "customer_name", "customer_phone", "customer_risk",
            "shipping_district", "total_amount", "cod_amount",
            "payment_status", "item_count", "created_at",
        ]

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    customer_detail = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()
    is_editable = serializers.BooleanField(read_only=True)
    amount_due = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + [
            "recipient_name", "recipient_phone", "shipping_thana",
            "shipping_area", "shipping_address",
            "subtotal", "discount_amount", "delivery_charge", "advance_paid",
            "amount_due", "internal_note", "customer_note",
            "confirmation_attempts", "last_call_outcome", "last_call_at",
            "cancel_reason", "cancel_note",
            "confirmed_at", "shipped_at", "delivered_at", "cancelled_at",
            "returned_at", "created_by_name",
            "items", "status_history", "customer_detail",
            "allowed_transitions", "is_editable",
        ]

    def get_customer_detail(self, obj):
        return CustomerLookupSerializer(obj.customer).data

    def get_allowed_transitions(self, obj):
        return obj.allowed_transitions()


class OrderCreateSerializer(serializers.Serializer):
    customer = serializers.IntegerField(required=False)
    new_customer = serializers.DictField(required=False)
    items = OrderItemInputSerializer(many=True)
    shipping = ShippingSerializer()
    source = serializers.ChoiceField(
        choices=OrderSource.choices, default=OrderSource.MANUAL
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0")
    )
    delivery_charge = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0")
    )
    advance_paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0")
    )
    internal_note = serializers.CharField(required=False, allow_blank=True)
    customer_note = serializers.CharField(required=False, allow_blank=True)
    acknowledge_duplicate = serializers.BooleanField(default=False)
    acknowledge_blacklist = serializers.BooleanField(default=False)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one item.")
        return value

    def validate(self, attrs):
        store = self.context["store"]

        customer = None
        if attrs.get("customer"):
            customer = Customer.objects.filter(
                pk=attrs["customer"], store=store
            ).first()
            if customer is None:
                raise serializers.ValidationError(
                    {"customer": "Unknown customer."}
                )
        elif attrs.get("new_customer"):
            from apps.customers.serializers import CustomerWriteSerializer

            nested = CustomerWriteSerializer(
                data=attrs["new_customer"], context=self.context
            )
            nested.is_valid(raise_exception=True)
            customer = nested.save()
        else:
            raise serializers.ValidationError(
                {"customer": "Provide a customer id or new_customer details."}
            )

        if customer.is_blacklisted and not attrs.get("acknowledge_blacklist"):
            raise serializers.ValidationError({
                "customer": (
                    "This customer is blacklisted: "
                    f"{customer.blacklist_reason or 'no reason recorded'}. "
                    "Resend with acknowledge_blacklist to place the order anyway."
                )
            })

        attrs["customer"] = customer
        return attrs


class OrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            "recipient_name", "recipient_phone", "shipping_district",
            "shipping_thana", "shipping_area", "shipping_address",
            "internal_note", "customer_note",
        ]


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    reason = serializers.ChoiceField(
        choices=CancelReason.choices, required=False, allow_blank=True
    )
    cancel_note = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )

    def validate(self, attrs):
        if attrs["status"] == OrderStatus.CANCELLED and not attrs.get("reason"):
            raise serializers.ValidationError(
                {"reason": "A reason is required to cancel an order."}
            )
        return attrs


class CallLogSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=CallOutcome.choices)
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )


class ItemsUpdateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one item.")
        return value


class BulkStatusSerializer(serializers.Serializer):
    order_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200
    )
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    reason = serializers.ChoiceField(
        choices=CancelReason.choices, required=False, allow_blank=True
    )


class DuplicateCheckSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    product_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
