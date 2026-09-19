from rest_framework import serializers

from .adapters.registry import get_adapter_class
from .models import Courier, StoreCourier

CREDENTIAL_FIELDS = {
    "pathao": ["client_id", "client_secret", "username", "password"],
    "steadfast": ["api_key", "secret_key"],
    "manual": [],
}


class CourierSerializer(serializers.ModelSerializer):
    required_credentials = serializers.SerializerMethodField()

    class Meta:
        model = Courier
        fields = [
            "id", "name", "code", "adapter_key", "logo", "website",
            "supports_api", "supports_webhook", "supports_quote",
            "supports_cancel", "is_active", "required_credentials",
        ]
        read_only_fields = fields

    def get_required_credentials(self, obj):
        return CREDENTIAL_FIELDS.get(obj.adapter_key, [])


class StoreCourierSerializer(serializers.ModelSerializer):
    courier_name = serializers.CharField(source="courier.name", read_only=True)
    courier_code = serializers.CharField(source="courier.code", read_only=True)
    adapter_key = serializers.CharField(
        source="courier.adapter_key", read_only=True
    )
    supports_api = serializers.BooleanField(
        source="courier.supports_api", read_only=True
    )
    has_credentials = serializers.BooleanField(read_only=True)
    can_book_via_api = serializers.BooleanField(read_only=True)

    class Meta:
        model = StoreCourier
        fields = [
            "id", "courier", "courier_name", "courier_code", "adapter_key",
            "supports_api", "config", "is_enabled", "is_default",
            "has_credentials", "can_book_via_api",
            "last_verified_at", "last_error", "created_at",
        ]
        read_only_fields = [
            "id", "has_credentials", "can_book_via_api",
            "last_verified_at", "last_error", "created_at",
        ]


class StoreCourierWriteSerializer(serializers.ModelSerializer):
    credentials = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        write_only=True,
    )

    class Meta:
        model = StoreCourier
        fields = ["id", "courier", "credentials", "config",
                  "is_enabled", "is_default"]
        read_only_fields = ["id"]

    def validate_courier(self, value):
        if not value.is_active:
            raise serializers.ValidationError(
                "That courier is not available."
            )
        return value

    def validate(self, attrs):
        courier = attrs.get("courier") or getattr(
            self.instance, "courier", None
        )
        credentials = attrs.get("credentials")

        if courier and credentials:
            required = CREDENTIAL_FIELDS.get(courier.adapter_key, [])
            missing = [f for f in required if not credentials.get(f)]
            if missing:
                raise serializers.ValidationError({
                    "credentials": (
                        f"{courier.name} needs: {', '.join(missing)}."
                    )
                })

        adapter_class = get_adapter_class(
            courier.adapter_key if courier else ""
        )
        if adapter_class is None:
            raise serializers.ValidationError(
                {"courier": "No adapter is installed for that courier."}
            )
        return attrs


class CredentialTestSerializer(serializers.Serializer):
    pass
