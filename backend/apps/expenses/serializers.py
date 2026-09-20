from rest_framework import serializers

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )

    class Meta:
        model = Expense
        fields = [
            "id", "date", "category", "category_display", "amount",
            "note", "attachment", "campaign_name", "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "created_by_name", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "The amount must be greater than zero."
            )
        return value
