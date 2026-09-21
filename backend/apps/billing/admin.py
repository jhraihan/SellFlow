from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "monthly_price", "order_limit",
                    "staff_limit", "allows_api_courier", "is_default",
                    "is_active"]
    list_filter = ["is_active", "is_default", "allows_api_courier"]
    search_fields = ["name", "code"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["store", "plan", "status", "orders_used",
                    "period_start", "period_end"]
    list_filter = ["status", "plan"]
    search_fields = ["store__name", "payment_reference"]
    autocomplete_fields = ["store"]
