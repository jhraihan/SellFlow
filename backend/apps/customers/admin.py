from django.contrib import admin

from .models import Customer, CustomerAddress


class CustomerAddressInline(admin.TabularInline):
    model = CustomerAddress
    extra = 0
    fields = ["label", "district", "thana", "address_line", "is_default"]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "store", "risk_level", "total_orders",
                    "returned_count", "lifetime_value"]
    list_filter = ["risk_level", "is_blacklisted"]
    search_fields = ["name", "phone", "store__name"]
    inlines = [CustomerAddressInline]
    readonly_fields = ["total_orders", "delivered_count", "returned_count",
                       "cancelled_count", "lifetime_value", "last_order_at"]


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ["customer", "district", "thana", "is_default"]
    search_fields = ["customer__name", "customer__phone", "district"]
