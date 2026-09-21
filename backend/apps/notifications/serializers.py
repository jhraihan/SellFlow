from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "id", "notification_type", "type_display", "level",
            "title", "body", "payload", "link",
            "is_read", "read_at", "created_at",
        ]
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    all = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("ids") and not attrs.get("all"):
            raise serializers.ValidationError(
                "Give a list of ids, or set all to true."
            )
        return attrs
