from django.contrib import admin

from .models import DeliveryStatusHistory, Shipment


class DeliveryStatusHistoryInline(admin.TabularInline):
    model = DeliveryStatusHistory
    extra = 0
    readonly_fields = ["raw_status", "mapped_status", "note", "location",
                       "source", "observed_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ["consignment_id", "order", "store_courier", "booking_mode",
                    "cod_amount", "cod_status", "current_courier_status",
                    "booked_at"]
    list_filter = ["booking_mode", "cod_status"]
    search_fields = ["consignment_id", "tracking_code",
                     "order__order_number"]
    readonly_fields = ["raw_booking_request", "raw_booking_response",
                       "last_synced_at", "sync_failures"]
    inlines = [DeliveryStatusHistoryInline]
    date_hierarchy = "created_at"


@admin.register(DeliveryStatusHistory)
class DeliveryStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["shipment", "raw_status", "mapped_status", "source",
                    "observed_at"]
    list_filter = ["source", "mapped_status"]
    search_fields = ["shipment__consignment_id"]
    readonly_fields = [f.name for f in DeliveryStatusHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
