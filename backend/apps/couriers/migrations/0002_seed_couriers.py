from django.db import migrations

COURIERS = [
    {
        "name": "Manual / Local rider",
        "code": "manual",
        "adapter_key": "manual",
        "supports_api": False,
        "supports_webhook": False,
        "supports_quote": False,
        "supports_cancel": True,
        "website": "",
    },
    {
        "name": "Pathao Courier",
        "code": "pathao",
        "adapter_key": "pathao",
        "supports_api": True,
        "supports_webhook": True,
        "supports_quote": True,
        "supports_cancel": False,
        "website": "https://pathao.com/courier/",
    },
    {
        "name": "Steadfast Courier",
        "code": "steadfast",
        "adapter_key": "steadfast",
        "supports_api": True,
        "supports_webhook": True,
        "supports_quote": False,
        "supports_cancel": False,
        "website": "https://steadfast.com.bd/",
    },
]


def seed(apps, schema_editor):
    Courier = apps.get_model("couriers", "Courier")
    for row in COURIERS:
        Courier.objects.update_or_create(code=row["code"], defaults=row)


def unseed(apps, schema_editor):
    Courier = apps.get_model("couriers", "Courier")
    Courier.objects.filter(
        code__in=[r["code"] for r in COURIERS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("couriers", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
