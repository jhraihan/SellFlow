import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.shipments.services import book_shipment
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

BOOK = "/api/v1/shipments/book/"
SHIPMENTS = "/api/v1/shipments/"
STORE_COURIERS = "/api/v1/couriers/store-couriers/"


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti", selling_price=Decimal("1200.00")
    )
    receive_stock(get_or_create_stock_item(product, None), 50)
    customer = Customer.objects.create(
        store=store, name="Karim Ahmed", phone="01712345678"
    )
    manual = StoreCourier.objects.create(
        store=store, courier=Courier.objects.get(code="manual"),
        is_default=True,
    )
    return {
        "owner": owner, "store": store, "product": product,
        "customer": customer, "manual": manual,
    }


def confirmed_order(shop):
    order = create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": 1}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )
    return transition_status(order, OrderStatus.CONFIRMED)


class TestCourierRegistryEndpoint:
    def test_lists_seeded_couriers(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            "/api/v1/couriers/"
        )

        assert response.status_code == 200
        codes = {row["code"] for row in response.data}
        assert {"manual", "pathao", "steadfast"} <= codes

    def test_reports_required_credentials(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            "/api/v1/couriers/"
        )
        pathao = next(r for r in response.data if r["code"] == "pathao")

        assert "client_id" in pathao["required_credentials"]


class TestStoreCourierEndpoint:
    def test_owner_can_enable_a_courier(self, shop, auth):
        steadfast = Courier.objects.get(code="steadfast")

        response = auth(shop["owner"], store=shop["store"]).post(
            STORE_COURIERS,
            {
                "courier": steadfast.id,
                "credentials": {"api_key": "k", "secret_key": "s"},
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["has_credentials"] is True

    def test_credentials_are_never_returned(self, shop, auth):
        steadfast = Courier.objects.get(code="steadfast")

        response = auth(shop["owner"], store=shop["store"]).post(
            STORE_COURIERS,
            {
                "courier": steadfast.id,
                "credentials": {"api_key": "SECRET", "secret_key": "ALSO"},
            },
            format="json",
        )

        body = json.dumps(response.data)
        assert "SECRET" not in body
        assert "ALSO" not in body
        assert "credentials" not in response.data

    def test_incomplete_credentials_rejected(self, shop, auth):
        pathao = Courier.objects.get(code="pathao")

        response = auth(shop["owner"], store=shop["store"]).post(
            STORE_COURIERS,
            {"courier": pathao.id, "credentials": {"client_id": "only"}},
            format="json",
        )
        assert response.status_code == 400

    def test_manager_cannot_manage_credentials(
        self, shop, auth, make_user, make_member
    ):
        manager = make_user(email="manager@example.com")
        make_member(shop["store"], manager, StoreRole.MANAGER)
        steadfast = Courier.objects.get(code="steadfast")

        response = auth(manager, store=shop["store"]).post(
            STORE_COURIERS,
            {"courier": steadfast.id, "credentials": {"api_key": "k",
                                                      "secret_key": "s"}},
            format="json",
        )
        assert response.status_code == 403

    def test_manual_courier_verifies_without_credentials(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            f"{STORE_COURIERS}{shop['manual'].id}/verify/", {}, format="json"
        )

        assert response.status_code == 200
        assert response.data["verified"] is True


class TestBookingEndpoint:
    def test_books_manually(self, shop, auth):
        order = confirmed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            BOOK,
            {
                "order": order.id,
                "store_courier": shop["manual"].id,
                "consignment_id": "LOCAL-555",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["consignment_id"] == "LOCAL-555"
        assert response.data["booking_mode"] == "manual"

    def test_booking_moves_order_to_shipped(self, shop, auth):
        order = confirmed_order(shop)

        auth(shop["owner"], store=shop["store"]).post(
            BOOK,
            {"order": order.id, "store_courier": shop["manual"].id,
             "consignment_id": "LOCAL-555"},
            format="json",
        )
        order.refresh_from_db()

        assert order.status == OrderStatus.SHIPPED

    def test_pending_order_is_rejected(self, shop, auth):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            BOOK,
            {"order": order.id, "store_courier": shop["manual"].id,
             "consignment_id": "X-1"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "ORDER_NOT_READY"

    def test_order_from_another_store_returns_404(
        self, shop, auth, make_user, make_store
    ):
        order = confirmed_order(shop)
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")
        other_courier = StoreCourier.objects.create(
            store=other_store, courier=Courier.objects.get(code="manual")
        )

        response = auth(stranger, store=other_store).post(
            BOOK,
            {"order": order.id, "store_courier": other_courier.id,
             "consignment_id": "X-1"},
            format="json",
        )

        assert response.status_code == 404
        order.refresh_from_db()
        assert order.status == OrderStatus.CONFIRMED

    def test_delivery_staff_cannot_book(
        self, shop, auth, make_user, make_member
    ):
        order = confirmed_order(shop)
        rider = make_user(email="rider@example.com")
        make_member(shop["store"], rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=shop["store"]).post(
            BOOK,
            {"order": order.id, "store_courier": shop["manual"].id,
             "consignment_id": "X-1"},
            format="json",
        )
        assert response.status_code == 403


class TestBulkBooking:
    def test_reports_per_order_outcome(self, shop, auth):
        first = confirmed_order(shop)
        second = confirmed_order(shop)
        pending = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        steadfast = StoreCourier.objects.create(
            store=shop["store"],
            courier=Courier.objects.get(code="steadfast"),
            credentials={"api_key": "k", "secret_key": "s"},
        )

        from apps.couriers.adapters.base import BookingResult

        results = [
            BookingResult(consignment_id="CN-1"),
            BookingResult(consignment_id="CN-2"),
        ]
        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            side_effect=results,
        ):
            response = auth(shop["owner"], store=shop["store"]).post(
                "/api/v1/shipments/bulk-book/",
                {
                    "order_ids": [first.id, second.id, pending.id],
                    "store_courier": steadfast.id,
                },
                format="json",
            )

        assert response.status_code == 200
        assert response.data["succeeded_count"] == 2
        assert response.data["failed_count"] == 1
        assert response.data["failed"][0]["code"] == "ORDER_NOT_READY"


class TestShipmentListing:
    def test_lists_store_shipments(self, shop, auth):
        order = confirmed_order(shop)
        book_shipment(order, shop["manual"], manual_consignment_id="X-1")

        response = auth(shop["owner"], store=shop["store"]).get(SHIPMENTS)

        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_search_by_consignment_id(self, shop, auth):
        order = confirmed_order(shop)
        book_shipment(order, shop["manual"], manual_consignment_id="FINDME-1")

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{SHIPMENTS}?search=FINDME"
        )
        assert len(response.data["results"]) == 1

    def test_manual_status_update_moves_order(self, shop, auth):
        order = confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            f"{SHIPMENTS}{shipment.id}/status/",
            {"raw_status": "delivered", "note": "Rider confirmed"},
            format="json",
        )

        assert response.status_code == 200
        order.refresh_from_db()
        assert order.status == OrderStatus.DELIVERED

    def test_actual_cost_can_be_recorded(self, shop, auth):
        order = confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            f"{SHIPMENTS}{shipment.id}/cost/",
            {"actual_cost": "85.00"},
            format="json",
        )

        assert response.status_code == 200
        assert Decimal(response.data["actual_cost"]) == Decimal("85.00")

    def test_cannot_read_another_stores_shipment(
        self, shop, auth, make_user, make_store
    ):
        order = confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).get(
            f"{SHIPMENTS}{shipment.id}/"
        )
        assert response.status_code == 404


class TestWebhook:
    def _shipment(self, shop):
        steadfast = StoreCourier.objects.create(
            store=shop["store"],
            courier=Courier.objects.get(code="steadfast"),
            credentials={"api_key": "k", "secret_key": "s"},
            config={"webhook_secret": "topsecret"},
        )
        order = confirmed_order(shop)
        from apps.couriers.adapters.base import BookingResult

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            return_value=BookingResult(consignment_id="CN-77"),
        ):
            return book_shipment(order, steadfast)

    def _sign(self, payload):
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hmac.new(
            b"topsecret", body.encode(), hashlib.sha256
        ).hexdigest()

    def test_signed_webhook_updates_the_order(self, shop, api):
        shipment = self._shipment(shop)
        payload = {"consignment_id": "CN-77", "status": "delivered"}

        response = api.post(
            "/api/v1/webhooks/courier/steadfast/",
            payload,
            format="json",
            HTTP_X_STEADFAST_SIGNATURE=self._sign(payload),
        )

        assert response.status_code == 202
        shipment.order.refresh_from_db()
        assert shipment.order.status == OrderStatus.DELIVERED

    def test_unsigned_webhook_is_rejected(self, shop, api):
        shipment = self._shipment(shop)
        payload = {"consignment_id": "CN-77", "status": "delivered"}

        response = api.post(
            "/api/v1/webhooks/courier/steadfast/", payload, format="json"
        )

        assert response.status_code == 401
        shipment.order.refresh_from_db()
        assert shipment.order.status == OrderStatus.SHIPPED

    def test_forged_signature_is_rejected(self, shop, api):
        self._shipment(shop)
        payload = {"consignment_id": "CN-77", "status": "delivered"}

        response = api.post(
            "/api/v1/webhooks/courier/steadfast/",
            payload,
            format="json",
            HTTP_X_STEADFAST_SIGNATURE="forged",
        )
        assert response.status_code == 401

    def test_unknown_consignment_is_accepted_quietly(self, shop, api):
        payload = {"consignment_id": "NOT-OURS", "status": "delivered"}

        response = api.post(
            "/api/v1/webhooks/courier/steadfast/", payload, format="json"
        )
        assert response.status_code == 202

    def test_unknown_courier_returns_404(self, api):
        response = api.post(
            "/api/v1/webhooks/courier/nosuchcourier/",
            {"consignment_id": "X"},
            format="json",
        )
        assert response.status_code == 404

    def test_payload_without_consignment_is_rejected(self, shop, api):
        response = api.post(
            "/api/v1/webhooks/courier/steadfast/", {}, format="json"
        )
        assert response.status_code == 400


class TestSyncCommand:
    def test_command_runs_without_error(self, shop):
        from io import StringIO

        from django.core.management import call_command

        order = confirmed_order(shop)
        book_shipment(order, shop["manual"], manual_consignment_id="X-1")

        out = StringIO()
        call_command("sync_tracking", stdout=out)

        assert "Synced" in out.getvalue()
