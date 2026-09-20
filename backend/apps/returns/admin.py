from django.contrib import admin

from .models import Return, ReturnItem


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ["order_item", "quantity", "condition", "restocked"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "store", "return_type", "reason",
                    "status", "total_loss", "refund_amount", "created_at"]
    list_filter = ["status", "reason", "return_type"]
    search_fields = ["order__order_number"]
    inlines = [ReturnItemInline]
    date_hierarchy = "created_at"

    @admin.display(description="Total loss")
    def total_loss(self, obj):
        return obj.total_loss
