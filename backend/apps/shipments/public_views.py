from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import normalise_bd_phone
from apps.orders.models import Order

from .models import Shipment

PUBLIC_STATUS_LABELS = {
    "pending": "Order received",
    "confirmed": "Order confirmed",
    "processing": "Being packed",
    "ready_to_ship": "Ready for pickup",
    "shipped": "Handed to courier",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "returned": "Returned",
    "cancelled": "Cancelled",
    "on_hold": "On hold",
}


def _mask_phone(phone):
    if not phone or len(phone) < 4:
        return ""
    return f"{'*' * (len(phone) - 4)}{phone[-4:]}"


@extend_schema(tags=["public"])
class PublicTrackingView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_track"

    def get(self, request):
        code = (request.query_params.get("code") or "").strip()
        order_number = (request.query_params.get("order_number") or "").strip()
        phone = (request.query_params.get("phone") or "").strip()

        order = None

        if code:
            shipment = (
                Shipment.objects.select_related("order__store", "store_courier__courier")
                .filter(cancelled_at__isnull=True)
                .filter(consignment_id=code)
                .first()
            )
            if shipment is None:
                shipment = (
                    Shipment.objects.select_related(
                        "order__store", "store_courier__courier"
                    )
                    .filter(cancelled_at__isnull=True, tracking_code=code)
                    .first()
                )
            if shipment is not None:
                order = shipment.order

        elif order_number and phone:
            try:
                normalised = normalise_bd_phone(phone)
            except Exception:
                normalised = phone
            order = (
                Order.objects.select_related("store", "customer")
                .filter(order_number__iexact=order_number)
                .filter(recipient_phone=normalised)
                .first()
            )

        else:
            return Response(
                {"error": {
                    "code": "TRACKING_INPUT_REQUIRED",
                    "message": (
                        "Provide a tracking code, or an order number together "
                        "with the phone number on the order."
                    ),
                    "details": {},
                }},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if order is None:
            return Response(
                {"found": False, "message": "No order matches those details."},
                status=http_status.HTTP_404_NOT_FOUND,
            )

        shipment = order.shipments.filter(cancelled_at__isnull=True).first()

        timeline = [
            {
                "status": row.to_status,
                "label": PUBLIC_STATUS_LABELS.get(row.to_status, row.to_status),
                "at": row.created_at,
            }
            for row in order.status_history.all()
            if row.to_status in PUBLIC_STATUS_LABELS
        ]

        return Response({
            "found": True,
            "order_number": order.order_number,
            "store_name": order.store.name,
            "status": order.status,
            "status_label": PUBLIC_STATUS_LABELS.get(order.status, order.status),
            "recipient_name": order.recipient_name,
            "recipient_phone": _mask_phone(order.recipient_phone),
            "district": order.shipping_district,
            "placed_at": order.created_at,
            "delivered_at": order.delivered_at,
            "courier": shipment.courier_name if shipment else None,
            "tracking_code": shipment.tracking_code if shipment else None,
            "tracking_url": shipment.tracking_url if shipment else None,
            "timeline": timeline,
        })
