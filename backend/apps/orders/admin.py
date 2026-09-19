from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product_name", "variant_label", "sku", "unit_price",
                       "unit_cost", "quantity", "line_total"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "note", "actor", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "store", "customer", "status",
                    "total_amount", "cod_amount", "payment_status",
                    "created_at"]
    list_filter = ["status", "source", "payment_status"]
    search_fields = ["order_number", "customer__name", "customer__phone",
                     "recipient_phone"]
    readonly_fields = ["order_number", "subtotal", "total_amount",
                       "cod_amount", "confirmed_at", "shipped_at",
                       "delivered_at", "cancelled_at", "returned_at"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    date_hierarchy = "created_at"


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["order", "from_status", "to_status", "actor", "created_at"]
    list_filter = ["to_status"]
    search_fields = ["order__order_number"]
    readonly_fields = [f.name for f in OrderStatusHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
