from rest_framework import serializers

from apps.orders.models import Order

from .models import (
    CourierSettlement,
    Payment,
    PaymentDirection,
    PaymentMethod,
    SettlementLine,
)


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(
        source="order.order_number", read_only=True
    )
    method_display = serializers.CharField(
        source="get_method_display", read_only=True
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "id", "order", "order_number", "method", "method_display",
            "direction", "amount", "reference", "note", "received_at",
            "recorded_by_name", "is_verified", "created_at",
        ]
        read_only_fields = ["id", "recorded_by_name", "created_at"]


class PaymentCreateSerializer(serializers.Serializer):
    order = serializers.IntegerField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    direction = serializers.ChoiceField(
        choices=PaymentDirection.choices, default=PaymentDirection.IN
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    received_at = serializers.DateTimeField(required=False)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "The amount must be greater than zero."
            )
        return value

    def validate_order(self, value):
        if value is None:
            return None
        store = self.context["store"]
        order = Order.objects.filter(pk=value, store=store).first()
        if order is None:
            raise serializers.ValidationError("Unknown order.")
        self.context["order_obj"] = order
        return value


class SettlementLineSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(
        source="shipment.order.order_number", read_only=True
    )
    difference = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = SettlementLine
        fields = [
            "id", "row_number", "consignment_id", "collected_amount",
            "deducted_charge", "net_amount", "expected_amount", "difference",
            "match_status", "shipment", "order_number", "note", "raw_row",
        ]
        read_only_fields = fields


class SettlementSerializer(serializers.ModelSerializer):
    courier_name = serializers.CharField(
        source="store_courier.courier.name", read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )
    line_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CourierSettlement
        fields = [
            "id", "store_courier", "courier_name", "statement_reference",
            "period_start", "period_end", "original_filename",
            "total_amount", "matched_count", "unmatched_count",
            "mismatch_count", "line_count", "status", "created_by_name",
            "committed_at", "created_at",
        ]
        read_only_fields = fields


class SettlementDetailSerializer(SettlementSerializer):
    lines = SettlementLineSerializer(many=True, read_only=True)

    class Meta(SettlementSerializer.Meta):
        fields = SettlementSerializer.Meta.fields + ["lines"]
        read_only_fields = fields


class SettlementUploadSerializer(serializers.Serializer):
    store_courier = serializers.IntegerField()
    file = serializers.FileField()
    statement_reference = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    period_start = serializers.DateField(required=False, allow_null=True)
    period_end = serializers.DateField(required=False, allow_null=True)


class SettlementCommitSerializer(serializers.Serializer):
    include_mismatches = serializers.BooleanField(default=False)
