from rest_framework import serializers

from .models import DeliveryStatusHistory, Shipment


class DeliveryStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryStatusHistory
        fields = [
            "id", "raw_status", "mapped_status", "note", "location",
            "source", "observed_at", "created_at",
        ]
        read_only_fields = fields


class ShipmentListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(
        source="order.order_number", read_only=True
    )
    order_status = serializers.CharField(source="order.status", read_only=True)
    customer_name = serializers.CharField(
        source="order.customer.name", read_only=True
    )
    courier_name = serializers.CharField(read_only=True)
    district = serializers.CharField(
        source="order.shipping_district", read_only=True
    )

    class Meta:
        model = Shipment
        fields = [
            "id", "order", "order_number", "order_status", "customer_name",
            "courier_name", "district", "consignment_id", "tracking_code",
            "tracking_url", "booking_mode", "cod_amount", "cod_status",
            "current_courier_status", "last_synced_at", "booked_at",
            "delivered_at", "cancelled_at", "created_at",
        ]
        read_only_fields = fields


class ShipmentDetailSerializer(ShipmentListSerializer):
    tracking_history = DeliveryStatusHistorySerializer(
        many=True, read_only=True
    )
    booked_by_name = serializers.CharField(
        source="booked_by.full_name", read_only=True
    )

    class Meta(ShipmentListSerializer.Meta):
        fields = ShipmentListSerializer.Meta.fields + [
            "quoted_cost", "actual_cost", "cod_collected_at",
            "cod_settled_at", "settlement_reference", "sync_failures",
            "booked_by_name", "tracking_history",
        ]
        read_only_fields = fields


class BookShipmentSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    store_courier = serializers.IntegerField()
    consignment_id = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )


class BulkBookSerializer(serializers.Serializer):
    order_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )
    store_courier = serializers.IntegerField()


class ManualStatusSerializer(serializers.Serializer):
    raw_status = serializers.CharField(max_length=80)
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )
    location = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )


class ShipmentCostSerializer(serializers.Serializer):
    actual_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
