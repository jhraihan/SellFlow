from rest_framework import serializers

from .models import Plan


class PlanSerializer(serializers.ModelSerializer):
    is_unlimited = serializers.BooleanField(read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id", "name", "code", "monthly_price", "order_limit",
            "is_unlimited", "staff_limit", "courier_limit", "sms_credits",
            "allows_api_courier", "allows_analytics", "is_default",
        ]
        read_only_fields = fields


class ActivatePlanSerializer(serializers.Serializer):
    plan = serializers.CharField(max_length=40)
    reference = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )

    def validate_plan(self, value):
        plan = Plan.objects.filter(code=value, is_active=True).first()
        if plan is None:
            raise serializers.ValidationError("Unknown plan.")
        self.context["plan_obj"] = plan
        return value
