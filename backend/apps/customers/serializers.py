
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import normalise_bd_phone

from .models import Customer, CustomerAddress


class CustomerAddressSerializer(serializers.ModelSerializer):
    full_address = serializers.CharField(read_only=True)

    class Meta:
        model = CustomerAddress
        fields = [
            "id", "label", "division", "district", "thana", "area",
            "address_line", "is_default", "full_address",
        ]
        read_only_fields = ["id", "full_address"]

    def validate_district(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("District is required.")
        return value


class CustomerListSerializer(serializers.ModelSerializer):
    return_rate = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )
    risk_level_display = serializers.CharField(
        source="get_risk_level_display", read_only=True
    )

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "risk_level", "risk_level_display",
            "is_blacklisted", "total_orders", "delivered_count",
            "returned_count", "return_rate", "lifetime_value",
            "last_order_at", "created_at",
        ]
        read_only_fields = [
            "id", "total_orders", "delivered_count", "returned_count",
            "return_rate", "lifetime_value", "last_order_at", "created_at",
        ]


class CustomerDetailSerializer(CustomerListSerializer):
    addresses = CustomerAddressSerializer(many=True, read_only=True)
    success_rate = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )
    shipped_count = serializers.IntegerField(read_only=True)

    class Meta(CustomerListSerializer.Meta):
        fields = CustomerListSerializer.Meta.fields + [
            "alt_phone", "facebook_url", "facebook_name", "notes",
            "blacklist_reason", "cancelled_count", "shipped_count",
            "success_rate", "addresses",
        ]


class CustomerWriteSerializer(serializers.ModelSerializer):
    address = CustomerAddressSerializer(required=False, write_only=True)

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "alt_phone",
            "facebook_url", "facebook_name", "notes", "address",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Customer name is too short.")
        return value

    def validate_phone(self, value):
        try:
            normalised = normalise_bd_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from None

        store = self.context.get("store")
        if store:
            clash = Customer.objects.filter(store=store, phone=normalised)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    "A customer with this phone number already exists."
                )
        return normalised

    def validate_alt_phone(self, value):
        if not value:
            return ""
        try:
            return normalise_bd_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from None

    def create(self, validated_data):
        address_data = validated_data.pop("address", None)
        store = self.context["store"]
        customer = Customer.objects.create(store=store, **validated_data)
        if address_data:
            address_data.setdefault("is_default", True)
            CustomerAddress.objects.create(
                store=store, customer=customer, **address_data
            )
        return customer

    def update(self, instance, validated_data):
        validated_data.pop("address", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class CustomerLookupSerializer(serializers.ModelSerializer):
    default_address = serializers.SerializerMethodField()
    return_rate = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone", "alt_phone",
            "risk_level", "is_blacklisted", "blacklist_reason",
            "total_orders", "delivered_count", "returned_count",
            "return_rate", "default_address",
        ]
        read_only_fields = fields

    def get_default_address(self, obj):
        address = next(
            (a for a in obj.addresses.all() if a.is_default), None
        ) or next(iter(obj.addresses.all()), None)
        if address is None:
            return None
        return CustomerAddressSerializer(address).data


class BlacklistSerializer(serializers.Serializer):
    is_blacklisted = serializers.BooleanField()
    reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )

    def validate(self, attrs):
        if attrs["is_blacklisted"] and not attrs.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": "Give a reason when blacklisting a customer."}
            )
        return attrs
