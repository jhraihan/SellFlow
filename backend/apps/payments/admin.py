from django.contrib import admin

from .models import CourierSettlement, Payment, SettlementLine


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "store", "order", "method", "direction", "amount",
                    "received_at"]
    list_filter = ["method", "direction"]
    search_fields = ["order__order_number", "reference"]
    date_hierarchy = "received_at"


class SettlementLineInline(admin.TabularInline):
    model = SettlementLine
    extra = 0
    readonly_fields = ["row_number", "consignment_id", "collected_amount",
                       "deducted_charge", "expected_amount", "match_status",
                       "shipment", "note"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CourierSettlement)
class CourierSettlementAdmin(admin.ModelAdmin):
    list_display = ["id", "store", "store_courier", "statement_reference",
                    "total_amount", "matched_count", "mismatch_count",
                    "unmatched_count", "status", "committed_at"]
    list_filter = ["status"]
    search_fields = ["statement_reference", "store__name"]
    inlines = [SettlementLineInline]
