from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from apps.orders.models import OrderStatus

from .. import http
from .base import (
    BookingResult,
    CourierAdapter,
    CourierRejected,
    PriceQuote,
    TrackingEvent,
)

SANDBOX_BASE = "https://courier-api-sandbox.pathao.com"
LIVE_BASE = "https://api-hermes.pathao.com"


class PathaoAdapter(CourierAdapter):
    code = "pathao"
    display_name = "Pathao Courier"
    supports_api = True
    supports_webhook = True
    supports_cancel = False
    supports_quote = True

    STATUS_MAP = {
        "pending": OrderStatus.SHIPPED,
        "pickup_requested": OrderStatus.SHIPPED,
        "assigned_for_pickup": OrderStatus.SHIPPED,
        "picked": OrderStatus.SHIPPED,
        "pickup": OrderStatus.SHIPPED,
        "at_the_sorting_hub": OrderStatus.SHIPPED,
        "in_transit": OrderStatus.SHIPPED,
        "received_at_last_mile_hub": OrderStatus.SHIPPED,
        "assigned_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
        "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
        "delivered": OrderStatus.DELIVERED,
        "partial_delivery": OrderStatus.DELIVERED,
        "delivery_failed": OrderStatus.OUT_FOR_DELIVERY,
        "returning": OrderStatus.RETURNED,
        "return": OrderStatus.RETURNED,
        "returned": OrderStatus.RETURNED,
        "cancelled": OrderStatus.CANCELLED,
    }

    @property
    def base_url(self):
        if self.config.get("sandbox", True):
            return SANDBOX_BASE
        return LIVE_BASE

    def _token_cache_key(self):
        client_id = self.credentials.get("client_id", "")
        return f"courier:pathao:token:{client_id}"

    def _access_token(self):
        cached = cache.get(self._token_cache_key())
        if cached:
            return cached

        payload = {
            "client_id": self.credentials.get("client_id"),
            "client_secret": self.credentials.get("client_secret"),
            "username": self.credentials.get("username"),
            "password": self.credentials.get("password"),
            "grant_type": "password",
        }
        response = http.request(
            self.code,
            "POST",
            f"{self.base_url}/aladdin/api/v1/issue-token",
            json_body=payload,
        )
        data = http.safe_json(response)
        token = data.get("access_token")
        expires = int(data.get("expires_in", 3600))
        if token:
            cache.set(self._token_cache_key(), token, max(expires - 60, 60))
        return token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def validate_credentials(self):
        required = ("client_id", "client_secret", "username", "password")
        missing = [f for f in required if not self.credentials.get(f)]
        if missing:
            raise CourierRejected(
                "Pathao credentials are incomplete.",
                code="COURIER_CREDENTIALS_INCOMPLETE",
                details={"missing": missing},
            )
        return bool(self._access_token())

    def _parcel_payload(self, draft):
        return {
            "store_id": self.config.get("store_id"),
            "merchant_order_id": draft.order_number,
            "recipient_name": draft.recipient_name,
            "recipient_phone": draft.recipient_phone,
            "recipient_address": draft.address_line,
            "recipient_city": self.config.get("city_id"),
            "recipient_zone": self.config.get("zone_id"),
            "delivery_type": self.config.get("delivery_type", 48),
            "item_type": self.config.get("item_type", 2),
            "item_quantity": draft.item_quantity,
            "item_weight": max(round(draft.weight_grams / 1000, 2), 0.5),
            "amount_to_collect": int(draft.cod_amount),
            "item_description": draft.item_description,
            "special_instruction": draft.special_instruction,
        }

    def create_parcel(self, draft):
        payload = self._parcel_payload(draft)
        response = http.request(
            self.code,
            "POST",
            f"{self.base_url}/aladdin/api/v1/orders",
            headers=self._headers(),
            json_body=payload,
        )
        data = http.safe_json(response)

        if response.status_code >= 400:
            raise CourierRejected(
                data.get("message", "Pathao rejected the parcel."),
                details={"errors": data.get("errors", {})},
            )

        body = data.get("data", data)
        consignment = body.get("consignment_id") or body.get("merchant_order_id")
        if not consignment:
            raise CourierRejected(
                "Pathao accepted the request but returned no consignment id.",
                details={"response": data},
            )

        return BookingResult(
            consignment_id=str(consignment),
            tracking_code=str(consignment),
            tracking_url=f"https://merchant.pathao.com/tracking?consignment_id={consignment}",
            quoted_cost=Decimal(str(body.get("delivery_fee", "0"))),
            raw_request=payload,
            raw_response=data,
        )

    def price_quote(self, draft):
        payload = {
            "store_id": self.config.get("store_id"),
            "item_type": self.config.get("item_type", 2),
            "delivery_type": self.config.get("delivery_type", 48),
            "item_weight": max(round(draft.weight_grams / 1000, 2), 0.5),
            "recipient_city": self.config.get("city_id"),
            "recipient_zone": self.config.get("zone_id"),
        }
        response = http.request(
            self.code,
            "POST",
            f"{self.base_url}/aladdin/api/v1/merchant/price-plan",
            headers=self._headers(),
            json_body=payload,
        )
        data = http.safe_json(response)
        body = data.get("data", data)
        return PriceQuote(
            amount=Decimal(str(body.get("price", "0"))),
            estimated_days=int(body.get("promo_discount", 0) or 0),
            raw_response=data,
        )

    def track(self, consignment_id):
        response = http.request(
            self.code,
            "GET",
            f"{self.base_url}/aladdin/api/v1/orders/{consignment_id}/info",
            headers=self._headers(),
        )
        data = http.safe_json(response)
        body = data.get("data", data)

        raw_status = body.get("order_status") or body.get("status") or ""
        if not raw_status:
            return []

        return [
            TrackingEvent(
                raw_status=str(raw_status),
                mapped_status=self.map_status(raw_status),
                note=body.get("order_status_text", "") or "",
                location=body.get("current_location", "") or "",
                observed_at=timezone.now(),
                raw_payload=data,
            )
        ]

    def parse_webhook(self, payload, headers=None):
        raw_status = (
            payload.get("event")
            or payload.get("order_status")
            or payload.get("status")
            or ""
        )
        if not raw_status:
            return []

        return [
            TrackingEvent(
                raw_status=str(raw_status),
                mapped_status=self.map_status(raw_status),
                note=payload.get("order_status_text", "") or "",
                location=payload.get("current_location", "") or "",
                observed_at=timezone.now(),
                raw_payload=payload,
            )
        ]

    def verify_webhook(self, payload, headers=None):
        expected = self.config.get("webhook_secret", "")
        if not expected:
            return False
        headers = headers or {}
        provided = headers.get("X-PATHAO-Signature") or headers.get(
            "HTTP_X_PATHAO_SIGNATURE", ""
        )
        return bool(provided) and provided == expected
