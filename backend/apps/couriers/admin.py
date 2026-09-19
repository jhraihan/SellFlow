from django.contrib import admin

from .models import Courier, StoreCourier


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "adapter_key", "supports_api",
                    "supports_webhook", "is_active"]
    list_filter = ["is_active", "supports_api"]
    search_fields = ["name", "code"]


@admin.register(StoreCourier)
class StoreCourierAdmin(admin.ModelAdmin):
    list_display = ["store", "courier", "is_enabled", "is_default",
                    "has_credentials", "last_verified_at"]
    list_filter = ["is_enabled", "is_default"]
    search_fields = ["store__name", "courier__name"]
    exclude = ["credentials"]

    @admin.display(boolean=True, description="Credentials stored")
    def has_credentials(self, obj):
        return obj.has_credentials
