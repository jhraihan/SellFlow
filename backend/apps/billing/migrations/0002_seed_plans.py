from decimal import Decimal

from django.db import migrations

PLANS = [
    {
        "name": "Free",
        "code": "free",
        "monthly_price": Decimal("0.00"),
        "order_limit": 50,
        "staff_limit": 1,
        "courier_limit": 1,
        "sms_credits": 0,
        "allows_api_courier": False,
        "allows_analytics": True,
        "sort_order": 1,
        "is_default": True,
    },
    {
        "name": "Starter",
        "code": "starter",
        "monthly_price": Decimal("990.00"),
        "order_limit": 500,
        "staff_limit": 3,
        "courier_limit": 2,
        "sms_credits": 200,
        "allows_api_courier": True,
        "allows_analytics": True,
        "sort_order": 2,
        "is_default": False,
    },
    {
        "name": "Growth",
        "code": "growth",
        "monthly_price": Decimal("2490.00"),
        "order_limit": 2000,
        "staff_limit": 8,
        "courier_limit": 5,
        "sms_credits": 1000,
        "allows_api_courier": True,
        "allows_analytics": True,
        "sort_order": 3,
        "is_default": False,
    },
    {
        "name": "Business",
        "code": "business",
        "monthly_price": Decimal("5990.00"),
        "order_limit": None,
        "staff_limit": 25,
        "courier_limit": 10,
        "sms_credits": 5000,
        "allows_api_courier": True,
        "allows_analytics": True,
        "sort_order": 4,
        "is_default": False,
    },
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for row in PLANS:
        Plan.objects.update_or_create(code=row["code"], defaults=row)


def unseed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code__in=[r["code"] for r in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
