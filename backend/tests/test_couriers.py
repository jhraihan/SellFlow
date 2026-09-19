from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.core.encryption import decrypt_text, encrypt_text
from apps.couriers.adapters.base import CourierRejected, ParcelDraft
from apps.couriers.adapters.manual import ManualAdapter
from apps.couriers.adapters.pathao import PathaoAdapter
from apps.couriers.adapters.registry import (
    available_adapters,
    build_adapter,
    get_adapter_class,
)
from apps.couriers.adapters.steadfast import SteadfastAdapter
from apps.couriers.models import Courier, StoreCourier
from apps.orders.models import OrderStatus

pytestmark = pytest.mark.django_db


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


PATHAO_BOOKING = {
    "message": "Order Created Successfully",
    "type": "success",
    "code": 200,
    "data": {
        "consignment_id": "DR2401151ABCD",
        "merchant_order_id": "RF-1001",
        "order_status": "Pending",
        "delivery_fee": 70,
    },
}

PATHAO_TRACKING = {
    "data": {
        "consignment_id": "DR2401151ABCD",
        "order_status": "Delivered",
        "order_status_text": "Parcel delivered to customer",
        "current_location": "Dhanmondi",
    }
}

STEADFAST_BOOKING = {
    "status": 200,
    "message": "Consignment has been created successfully.",
    "consignment": {
        "consignment_id": 1424107,
        "invoice": "RF-1001",
        "tracking_code": "A1B2C3D4",
        "status": "in_review",
        "cod_amount": 1500,
    },
}

STEADFAST_TRACKING = {"status": 200, "delivery_status": "delivered"}


@pytest.fixture
def draft():
    return ParcelDraft(
        order_number="RF-1001",
        recipient_name="Karim Ahmed",
        recipient_phone="+8801712345678",
        address_line="House 12, Road 4",
        district="Dhaka",
        thana="Dhanmondi",
        cod_amount=Decimal("1500.00"),
        item_description="Cotton Kurti x1",
        weight_grams=500,
    )


class TestEncryption:
    def test_round_trip(self):
        assert decrypt_text(encrypt_text("secret-value")) == "secret-value"

    def test_ciphertext_does_not_contain_plaintext(self):
        token = encrypt_text("my-api-key")
        assert "my-api-key" not in token

    def test_blank_values_pass_through(self):
        assert encrypt_text("") == ""
        assert decrypt_text("") == ""

    def test_corrupt_token_returns_blank(self):
        assert decrypt_text("not-a-real-token") == ""

    def test_credentials_are_encrypted_at_rest(self, make_user, make_store):
        from django.db import connection

        store = make_store(make_user())
        courier = Courier.objects.get(code="steadfast")
        link = StoreCourier.objects.create(
            store=store,
            courier=courier,
            credentials={"api_key": "SECRET123", "secret_key": "TOPSECRET"},
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT credentials FROM couriers_store_courier WHERE id = %s",
                [link.id],
            )
            stored = cursor.fetchone()[0]

        assert "SECRET123" not in stored
        assert "TOPSECRET" not in stored

        link.refresh_from_db()
        assert link.credentials["api_key"] == "SECRET123"


class TestRegistry:
    def test_known_adapters_resolve(self):
        assert get_adapter_class("manual") is ManualAdapter
        assert get_adapter_class("pathao") is PathaoAdapter
        assert get_adapter_class("steadfast") is SteadfastAdapter

    def test_unknown_adapter_returns_none(self):
        assert get_adapter_class("nope") is None

    def test_unknown_adapter_falls_back_to_manual(
        self, make_user, make_store
    ):
        store = make_store(make_user())
        courier = Courier.objects.create(
            name="Mystery", code="mystery", adapter_key="not_installed"
        )
        link = StoreCourier.objects.create(store=store, courier=courier)

        assert isinstance(build_adapter(link), ManualAdapter)

    def test_available_adapters_lists_capabilities(self):
        codes = {a["code"] for a in available_adapters()}
        assert {"manual", "pathao", "steadfast"} <= codes


class TestStatusMapping:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Delivered", OrderStatus.DELIVERED),
            ("delivered", OrderStatus.DELIVERED),
            ("Pickup", OrderStatus.SHIPPED),
            ("In Transit", OrderStatus.SHIPPED),
            ("Assigned for Delivery", OrderStatus.OUT_FOR_DELIVERY),
            ("Returned", OrderStatus.RETURNED),
        ],
    )
    def test_pathao_maps_known_statuses(self, raw, expected):
        assert PathaoAdapter().map_status(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("delivered", OrderStatus.DELIVERED),
            ("partial_delivered", OrderStatus.DELIVERED),
            ("cancelled", OrderStatus.RETURNED),
            ("in_review", OrderStatus.SHIPPED),
        ],
    )
    def test_steadfast_maps_known_statuses(self, raw, expected):
        assert SteadfastAdapter().map_status(raw) == expected

    def test_unknown_status_maps_to_blank(self):
        assert PathaoAdapter().map_status("teleported_to_mars") == ""
        assert SteadfastAdapter().map_status("???") == ""

    def test_none_status_is_safe(self):
        assert PathaoAdapter().map_status(None) == ""

    def test_every_mapped_status_is_a_real_order_status(self):
        valid = set(OrderStatus.values)
        for adapter in (PathaoAdapter, SteadfastAdapter, ManualAdapter):
            for mapped in adapter.STATUS_MAP.values():
                assert mapped in valid, f"{adapter.code}: {mapped}"


class TestPathaoAdapter:
    def _adapter(self):
        return PathaoAdapter(
            credentials={
                "client_id": "cid", "client_secret": "csec",
                "username": "u", "password": "p",
            },
            config={"store_id": 1, "city_id": 1, "zone_id": 2,
                    "sandbox": True},
        )

    def test_create_parcel_returns_consignment(self, draft):
        adapter = self._adapter()
        with patch.object(adapter, "_access_token", return_value="tok"), \
             patch("apps.couriers.http.request",
                   return_value=FakeResponse(PATHAO_BOOKING)):
            result = adapter.create_parcel(draft)

        assert result.consignment_id == "DR2401151ABCD"
        assert result.quoted_cost == Decimal("70")
        assert "DR2401151ABCD" in result.tracking_url

    def test_payload_sends_cod_and_recipient(self, draft):
        adapter = self._adapter()
        captured = {}

        def capture(code, method, url, **kwargs):
            captured.update(kwargs.get("json_body") or {})
            return FakeResponse(PATHAO_BOOKING)

        with patch.object(adapter, "_access_token", return_value="tok"), \
             patch("apps.couriers.http.request", side_effect=capture):
            adapter.create_parcel(draft)

        assert captured["recipient_name"] == "Karim Ahmed"
        assert captured["amount_to_collect"] == 1500
        assert captured["merchant_order_id"] == "RF-1001"

    def test_rejection_raises_courier_rejected(self, draft):
        adapter = self._adapter()
        error = {"message": "Invalid zone", "errors": {"zone": ["bad"]}}

        with patch.object(adapter, "_access_token", return_value="tok"), \
             patch("apps.couriers.http.request",
                   return_value=FakeResponse(error, status_code=422)):
            with pytest.raises(CourierRejected) as exc:
                adapter.create_parcel(draft)

        assert "Invalid zone" in exc.value.message

    def test_missing_consignment_is_rejected(self, draft):
        adapter = self._adapter()
        with patch.object(adapter, "_access_token", return_value="tok"), \
             patch("apps.couriers.http.request",
                   return_value=FakeResponse({"data": {}})):
            with pytest.raises(CourierRejected):
                adapter.create_parcel(draft)

    def test_track_returns_mapped_event(self):
        adapter = self._adapter()
        with patch.object(adapter, "_access_token", return_value="tok"), \
             patch("apps.couriers.http.request",
                   return_value=FakeResponse(PATHAO_TRACKING)):
            events = adapter.track("DR2401151ABCD")

        assert len(events) == 1
        assert events[0].mapped_status == OrderStatus.DELIVERED
        assert events[0].location == "Dhanmondi"

    def test_incomplete_credentials_rejected(self):
        adapter = PathaoAdapter(credentials={"client_id": "only-this"})
        with pytest.raises(CourierRejected) as exc:
            adapter.validate_credentials()
        assert "missing" in exc.value.details

    def test_webhook_signature_required(self):
        adapter = PathaoAdapter(config={"webhook_secret": "shhh"})

        assert adapter.verify_webhook({}, {"X-PATHAO-Signature": "shhh"})
        assert not adapter.verify_webhook({}, {"X-PATHAO-Signature": "wrong"})
        assert not adapter.verify_webhook({}, {})

    def test_webhook_rejected_when_no_secret_configured(self):
        assert not PathaoAdapter().verify_webhook(
            {}, {"X-PATHAO-Signature": "anything"}
        )


class TestSteadfastAdapter:
    def _adapter(self):
        return SteadfastAdapter(
            credentials={"api_key": "key", "secret_key": "secret"}
        )

    def test_create_parcel_returns_consignment(self, draft):
        adapter = self._adapter()
        with patch("apps.couriers.http.request",
                   return_value=FakeResponse(STEADFAST_BOOKING)):
            result = adapter.create_parcel(draft)

        assert result.consignment_id == "1424107"
        assert result.tracking_code == "A1B2C3D4"

    def test_phone_is_sent_without_country_code(self, draft):
        adapter = self._adapter()
        captured = {}

        def capture(code, method, url, **kwargs):
            captured.update(kwargs.get("json_body") or {})
            return FakeResponse(STEADFAST_BOOKING)

        with patch("apps.couriers.http.request", side_effect=capture):
            adapter.create_parcel(draft)

        assert captured["recipient_phone"] == "01712345678"

    def test_address_is_flattened(self, draft):
        adapter = self._adapter()
        captured = {}

        def capture(code, method, url, **kwargs):
            captured.update(kwargs.get("json_body") or {})
            return FakeResponse(STEADFAST_BOOKING)

        with patch("apps.couriers.http.request", side_effect=capture):
            adapter.create_parcel(draft)

        assert "Dhanmondi" in captured["recipient_address"]
        assert "Dhaka" in captured["recipient_address"]

    def test_non_200_body_is_rejected(self, draft):
        adapter = self._adapter()
        with patch("apps.couriers.http.request",
                   return_value=FakeResponse({"status": 400,
                                              "message": "Bad phone"})):
            with pytest.raises(CourierRejected):
                adapter.create_parcel(draft)

    def test_track_maps_status(self):
        adapter = self._adapter()
        with patch("apps.couriers.http.request",
                   return_value=FakeResponse(STEADFAST_TRACKING)):
            events = adapter.track("1424107")

        assert events[0].mapped_status == OrderStatus.DELIVERED

    def test_hmac_webhook_verification(self):
        import hashlib
        import hmac
        import json

        adapter = SteadfastAdapter(config={"webhook_secret": "topsecret"})
        payload = {"consignment_id": "1424107", "status": "delivered"}
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(
            b"topsecret", body.encode(), hashlib.sha256
        ).hexdigest()

        assert adapter.verify_webhook(
            payload, {"X-Steadfast-Signature": signature}
        )
        assert not adapter.verify_webhook(
            payload, {"X-Steadfast-Signature": "forged"}
        )


class TestManualAdapter:
    def test_needs_no_credentials(self):
        assert ManualAdapter().validate_credentials() is True

    def test_track_returns_nothing(self):
        assert ManualAdapter().track("anything") == []

    def test_builds_events_for_manual_updates(self):
        event = ManualAdapter().build_event("delivered", note="Rider confirmed")
        assert event.mapped_status == OrderStatus.DELIVERED
        assert event.note == "Rider confirmed"


class TestStoreCourierModel:
    def test_manual_courier_cannot_book_via_api(self, make_user, make_store):
        store = make_store(make_user())
        link = StoreCourier.objects.create(
            store=store, courier=Courier.objects.get(code="manual")
        )
        assert link.can_book_via_api is False

    def test_api_courier_without_credentials_cannot_book(
        self, make_user, make_store
    ):
        store = make_store(make_user())
        link = StoreCourier.objects.create(
            store=store, courier=Courier.objects.get(code="pathao")
        )
        assert link.has_credentials is False
        assert link.can_book_via_api is False

    def test_api_courier_with_credentials_can_book(
        self, make_user, make_store
    ):
        store = make_store(make_user())
        link = StoreCourier.objects.create(
            store=store,
            courier=Courier.objects.get(code="steadfast"),
            credentials={"api_key": "k", "secret_key": "s"},
        )
        assert link.can_book_via_api is True

    def test_only_one_default_per_store(self, make_user, make_store):
        store = make_store(make_user())
        first = StoreCourier.objects.create(
            store=store,
            courier=Courier.objects.get(code="manual"),
            is_default=True,
        )
        second = StoreCourier.objects.create(
            store=store,
            courier=Courier.objects.get(code="pathao"),
            is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.is_default is False
        assert second.is_default is True
