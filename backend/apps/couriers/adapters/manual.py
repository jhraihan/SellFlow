from apps.orders.models import OrderStatus

from .base import CourierAdapter, TrackingEvent


class ManualAdapter(CourierAdapter):
    code = "manual"
    display_name = "Manual / Local rider"
    supports_api = False
    supports_webhook = False
    supports_cancel = True
    supports_quote = False

    STATUS_MAP = {
        "picked_up": OrderStatus.SHIPPED,
        "in_transit": OrderStatus.SHIPPED,
        "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
        "delivered": OrderStatus.DELIVERED,
        "returned": OrderStatus.RETURNED,
        "cancelled": OrderStatus.CANCELLED,
    }

    def validate_credentials(self):
        return True

    def track(self, consignment_id):
        return []

    def cancel(self, consignment_id):
        return True

    def build_event(self, raw_status, note="", location=""):
        return TrackingEvent(
            raw_status=raw_status,
            mapped_status=self.map_status(raw_status),
            note=note,
            location=location,
        )
