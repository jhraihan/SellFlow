import hashlib
import hmac
from decimal import Decimal

from django.utils import timezone

from apps.orders.models import OrderStatus

from .. import http
from .base import BookingResult, CourierAdapter, CourierRejected, TrackingEvent

BASE_URL = "https://portal.packzy.com/api/v1"


class SteadfastAdapter(CourierAdapter):
    code = "steadfast"
    display_name = "Steadfast Courier"
    supports_api = True
    supports_webhook = True
    supports_cancel = False
    supports_quote = False

    STATUS_MAP = {
        "pending": OrderStatus.SHIPPED,
        "in_review": OrderStatus.SHIPPED,
        "hold": OrderStatus.SHIPPED,
        "delivered_approval_pending": OrderStatus.OUT_FOR_DELIVERY,
        "partial_delivered_approval_pending": OrderStatus.OUT_FOR_DELIVERY,
        "cancelled_approval_pending": OrderStatus.OUT_FOR_DELIVERY,
        "unknown_approval_pending": OrderStatus.OUT_FOR_DELIVERY,
        "delivered": OrderStatus.DELIVERED,
        "partial_delivered": OrderStatus.DELIVERED,
        "cancelled": OrderStatus.RETURNED,
        "unknown": OrderStatus.SHIPPED,
        "returned": OrderStatus.RETURNED,
    }

    def _headers(self):
        return {
            "Api-Key": self.credentials.get("api_key", ""),
            "Secret-Key": self.credentials.get("secret_key", ""),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def validate_credentials(self):
        missing = [
            f for f in ("api_key", "secret_key")
            if not self.credentials.get(f)
        ]
        if missing:
            raise CourierRejected(
                "Steadfast credentials are incomplete.",
                code="COURIER_CREDENTIALS_INCOMPLETE",
                details={"missing": missing},
            )
        return True

    def create_parcel(self, draft):
        address = ", ".join(
            part for part in (
                draft.address_line, draft.area, draft.thana, draft.district
            ) if part
        )
        payload = {
            "invoice": draft.order_number,
            "recipient_name": draft.recipient_name,
            "recipient_phone": draft.recipient_phone.replace("+88", ""),
            "recipient_address": address,
            "cod_amount": float(draft.cod_amount),
            "note": draft.special_instruction or draft.item_description,
        }

        response = http.request(
            self.code,
            "POST",
            f"{BASE_URL}/create_order",
            headers=self._headers(),
            json_body=payload,
        )
        data = http.safe_json(response)

        if response.status_code >= 400 or data.get("status") not in (200, "200"):
            raise CourierRejected(
                data.get("message", "Steadfast rejected the parcel."),
                details={"errors": data.get("errors", {})},
            )

        consignment = data.get("consignment", {})
        consignment_id = consignment.get("consignment_id")
        tracking_code = consignment.get("tracking_code", "")

        if not consignment_id:
            raise CourierRejected(
                "Steadfast accepted the request but returned no consignment id.",
                details={"response": data},
            )

        return BookingResult(
            consignment_id=str(consignment_id),
            tracking_code=str(tracking_code),
            tracking_url=f"https://steadfast.com.bd/t/{tracking_code}",
            quoted_cost=Decimal("0.00"),
            raw_request=payload,
            raw_response=data,
        )

    def track(self, consignment_id):
        response = http.request(
            self.code,
            "GET",
            f"{BASE_URL}/status_by_cid/{consignment_id}",
            headers=self._headers(),
        )
        data = http.safe_json(response)

        raw_status = data.get("delivery_status") or ""
        if not raw_status:
            return []

        return [
            TrackingEvent(
                raw_status=str(raw_status),
                mapped_status=self.map_status(raw_status),
                note="",
                observed_at=timezone.now(),
                raw_payload=data,
            )
        ]

    def parse_webhook(self, payload, headers=None):
        raw_status = payload.get("status") or payload.get("delivery_status") or ""
        if not raw_status:
            return []

        return [
            TrackingEvent(
                raw_status=str(raw_status),
                mapped_status=self.map_status(raw_status),
                note=payload.get("note", "") or "",
                observed_at=timezone.now(),
                raw_payload=payload,
            )
        ]

    def verify_webhook(self, payload, headers=None):
        secret = self.config.get("webhook_secret", "")
        if not secret:
            return False

        headers = headers or {}
        provided = (
            headers.get("X-Steadfast-Signature")
            or headers.get("HTTP_X_STEADFAST_SIGNATURE", "")
        )
        if not provided:
            return False

        import json

        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        expected = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided)
