from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.core.exceptions import APIError


class CourierError(APIError):
    default_code = "COURIER_ERROR"
    default_detail = "The courier could not process this request."


class CourierAuthError(CourierError):
    default_code = "COURIER_AUTH_FAILED"
    default_detail = "The courier rejected the stored credentials."


class CourierUnavailable(CourierError):
    default_code = "COURIER_UNAVAILABLE"
    default_detail = "The courier service is not responding."


class CourierRejected(CourierError):
    default_code = "COURIER_REJECTED_PARCEL"
    default_detail = "The courier rejected the parcel details."


@dataclass
class ParcelDraft:
    order_number: str
    recipient_name: str
    recipient_phone: str
    address_line: str
    district: str
    thana: str = ""
    area: str = ""
    cod_amount: Decimal = Decimal("0.00")
    item_description: str = ""
    item_quantity: int = 1
    weight_grams: int = 500
    special_instruction: str = ""


@dataclass
class BookingResult:
    consignment_id: str
    tracking_code: str = ""
    tracking_url: str = ""
    quoted_cost: Decimal = Decimal("0.00")
    raw_request: dict = field(default_factory=dict)
    raw_response: dict = field(default_factory=dict)


@dataclass
class TrackingEvent:
    raw_status: str
    mapped_status: str
    note: str = ""
    location: str = ""
    observed_at: datetime = None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class PriceQuote:
    amount: Decimal
    currency: str = "BDT"
    estimated_days: int = 0
    raw_response: dict = field(default_factory=dict)


class CourierAdapter:
    code = ""
    display_name = ""
    supports_api = False
    supports_webhook = False
    supports_cancel = False
    supports_quote = False

    STATUS_MAP = {}

    def __init__(self, credentials=None, config=None):
        self.credentials = credentials or {}
        self.config = config or {}

    def map_status(self, raw_status):
        if raw_status is None:
            return ""
        key = str(raw_status).strip().lower().replace(" ", "_")
        return self.STATUS_MAP.get(key, "")

    def validate_credentials(self):
        return True

    def price_quote(self, draft):
        raise NotImplementedError(
            f"{self.display_name} does not support price quotes."
        )

    def create_parcel(self, draft):
        raise NotImplementedError(
            f"{self.display_name} does not support API booking."
        )

    def track(self, consignment_id):
        raise NotImplementedError(
            f"{self.display_name} does not support tracking."
        )

    def cancel(self, consignment_id):
        raise NotImplementedError(
            f"{self.display_name} does not support cancellation."
        )

    def parse_webhook(self, payload, headers=None):
        raise NotImplementedError(
            f"{self.display_name} does not support webhooks."
        )

    def verify_webhook(self, payload, headers=None):
        return False
