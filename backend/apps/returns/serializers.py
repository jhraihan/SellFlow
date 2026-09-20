from rest_framework import serializers

from apps.orders.models import Order

from .models import (
    ItemCondition,
    Return,
    ReturnItem,
    ReturnReason,
    ReturnType,
)


class ReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="order_item.product_name", read_only=True
    )
    variant_label = serializers.CharField(
        source="order_item.variant_label", read_only=True
    )
    unit_price = serializers.DecimalField(
        source="order_item.unit_price", max_digits=12, decimal_places=2,
        read_only=True,
    )
    value = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = ReturnItem
        fields = [
            "id", "order_item", "product_name", "variant_label",
            "unit_price", "quantity", "value", "condition", "restocked",
            "note",
        ]
        read_only_fields = ["id", "restocked"]


class ReturnListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(
        source="order.order_number", read_only=True
    )
    customer_name = serializers.CharField(
        source="order.customer.name", read_only=True
    )
    reason_display = serializers.CharField(
        source="get_reason_display", read_only=True
    )
    total_loss = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Return
        fields = [
            "id", "order", "order_number", "customer_name", "return_type",
            "reason", "reason_display", "status", "forward_delivery_cost",
            "return_charge", "written_off_value", "refund_amount",
            "total_loss", "received_at", "resolved_at", "created_at",
        ]
        read_only_fields = fields


class ReturnDetailSerializer(ReturnListSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )
    consignment_id = serializers.CharField(
        source="shipment.consignment_id", read_only=True
    )

    class Meta(ReturnListSerializer.Meta):
        fields = ReturnListSerializer.Meta.fields + [
            "shipment", "consignment_id", "reason_note", "resolution_note",
            "created_by_name", "items",
        ]
        read_only_fields = fields


class ReturnItemInputSerializer(serializers.Serializer):
    order_item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(
        choices=ItemCondition.choices, default=ItemCondition.SELLABLE
    )
    note = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )


class ReturnCreateSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=ReturnReason.choices)
    reason_note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    return_type = serializers.ChoiceField(
        choices=ReturnType.choices, required=False
    )
    items = ReturnItemInputSerializer(many=True, required=False)
    return_charge = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )

    def validate_order(self, value):
        store = self.context["store"]
        order = Order.objects.filter(pk=value, store=store).first()
        if order is None:
            raise serializers.ValidationError("Unknown order.")
        self.context["order_obj"] = order
        return value

    def validate(self, attrs):
        order = self.context.get("order_obj")
        if order is None:
            return attrs

        valid_ids = {i.id for i in order.items.all()}
        for row in attrs.get("items") or []:
            if row["order_item"] not in valid_ids:
                raise serializers.ValidationError({
                    "items": f"Item {row['order_item']} is not on this order."
                })
        return attrs


class ItemDispositionSerializer(serializers.Serializer):
    return_item = serializers.IntegerField()
    condition = serializers.ChoiceField(choices=ItemCondition.choices)
    restock = serializers.BooleanField(default=True)


class ResolveReturnSerializer(serializers.Serializer):
    item_dispositions = ItemDispositionSerializer(many=True, required=False)
    refund_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    refund_method = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    resolution_note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
