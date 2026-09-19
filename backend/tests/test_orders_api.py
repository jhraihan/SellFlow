from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.customers.models import Customer
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store,
        name="Cotton Kurti",
        selling_price=Decimal("1200.00"),
        cost_price=Decimal("700.00"),
    )
    receive_stock(get_or_create_stock_item(product, None), 50)
    customer = Customer.objects.create(
        store=store, name="Karim Ahmed", phone="01712345678"
    )
    return {
        "owner": owner, "store": store,
        "product": product, "customer": customer,
    }


def order_payload(shop, **overrides):
    payload = {
        "customer": shop["customer"].id,
        "items": [{"product": shop["product"].id, "quantity": 2}],
        "shipping": {
            "district": "Dhaka",
            "thana": "Dhanmondi",
            "address_line": "House 12, Road 4",
        },
        "source": "messenger",
    }
    payload.update(overrides)
    return payload


def seed_order(shop, quantity=2):
    return create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )


class TestOrderCreateEndpoint:
    def test_creates_order(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, order_payload(shop), format="json"
        )

        assert response.status_code == 201
        assert response.data["status"] == OrderStatus.PENDING
        assert Decimal(response.data["total_amount"]) == Decimal("2460.00")
        assert Decimal(response.data["cod_amount"]) == Decimal("2460.00")

    def test_creates_customer_inline(self, shop, auth):
        payload = order_payload(shop)
        payload.pop("customer")
        payload["new_customer"] = {
            "name": "Nasrin Akter", "phone": "01911223344"
        }

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, payload, format="json"
        )

        assert response.status_code == 201
        assert Customer.objects.filter(
            store=shop["store"], phone="+8801911223344"
        ).exists()

    def test_requires_a_customer(self, shop, auth):
        payload = order_payload(shop)
        payload.pop("customer")

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, payload, format="json"
        )
        assert response.status_code == 400

    def test_rejects_unknown_product(self, shop, auth):
        payload = order_payload(shop, items=[{"product": 99999, "quantity": 1}])

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, payload, format="json"
        )
        assert response.status_code == 400

    def test_blacklisted_customer_blocks_order(self, shop, auth):
        shop["customer"].is_blacklisted = True
        shop["customer"].blacklist_reason = "Repeated fake orders"
        shop["customer"].save()

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, order_payload(shop), format="json"
        )

        assert response.status_code == 400
        assert "blacklisted" in str(response.data["error"]).lower()

    def test_blacklist_can_be_overridden_explicitly(self, shop, auth):
        shop["customer"].is_blacklisted = True
        shop["customer"].save()

        payload = order_payload(shop, acknowledge_blacklist=True)
        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, payload, format="json"
        )
        assert response.status_code == 201

    def test_duplicate_order_returns_conflict(self, shop, auth):
        seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, order_payload(shop), format="json"
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == "POSSIBLE_DUPLICATE"

    def test_duplicate_can_be_acknowledged(self, shop, auth):
        seed_order(shop)
        payload = order_payload(shop, acknowledge_duplicate=True)

        response = auth(shop["owner"], store=shop["store"]).post(
            ORDERS, payload, format="json"
        )
        assert response.status_code == 201


class TestStatusEndpoint:
    def test_confirms_an_order(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "confirmed", "note": "Called customer"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == OrderStatus.CONFIRMED

    def test_illegal_transition_returns_409(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "delivered"},
            format="json",
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == "INVALID_TRANSITION"
        assert "allowed" in response.data["error"]["details"]

    def test_insufficient_stock_returns_409(self, shop, auth):
        order = seed_order(shop, quantity=80)

        response = auth(shop["owner"], store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "confirmed"},
            format="json",
        )

        assert response.status_code == 409
        assert response.data["error"]["code"] == "INSUFFICIENT_STOCK"

    def test_cancel_requires_reason(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "cancelled"},
            format="json",
        )
        assert response.status_code == 400

    def test_cancel_with_reason_succeeds(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "cancelled", "reason": "fake_order"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["cancel_reason"] == "fake_order"


class TestConfirmEndpoint:
    def test_confirmed_outcome_moves_status(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            f"{ORDERS}{order.id}/confirm/",
            {"outcome": "confirmed"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == OrderStatus.CONFIRMED
        assert response.data["confirmation_attempts"] == 1

    def test_no_answer_keeps_pending(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            f"{ORDERS}{order.id}/confirm/",
            {"outcome": "no_answer"},
            format="json",
        )

        assert response.data["status"] == OrderStatus.PENDING
        assert response.data["confirmation_attempts"] == 1


class TestListingAndFilters:
    def test_search_by_order_number(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{ORDERS}?search={order.order_number}"
        )

        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_search_by_customer_phone(self, shop, auth):
        seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{ORDERS}?search=01712345678"
        )
        assert len(response.data["results"]) == 1

    def test_filter_by_status(self, shop, auth):
        first = seed_order(shop)
        transition_status(first, OrderStatus.CONFIRMED)
        seed_order(shop)

        client = auth(shop["owner"], store=shop["store"])
        confirmed = client.get(f"{ORDERS}?status=confirmed")
        pending = client.get(f"{ORDERS}?status=pending")

        assert len(confirmed.data["results"]) == 1
        assert len(pending.data["results"]) == 1

    def test_stats_endpoint_counts_by_status(self, shop, auth):
        first = seed_order(shop)
        transition_status(first, OrderStatus.CONFIRMED)
        seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{ORDERS}stats/"
        )

        assert response.data["total"] == 2
        assert response.data["by_status"]["confirmed"] == 1
        assert response.data["by_status"]["pending"] == 1


class TestBulkStatus:
    def test_bulk_confirm_reports_per_order_results(self, shop, auth):
        first = seed_order(shop)
        second = seed_order(shop)
        already = seed_order(shop)
        transition_status(already, OrderStatus.CANCELLED, reason="duplicate")

        response = auth(shop["owner"], store=shop["store"]).post(
            "/api/v1/orders/bulk-status/",
            {
                "order_ids": [first.id, second.id, already.id],
                "status": "confirmed",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["succeeded_count"] == 2
        assert response.data["failed_count"] == 1
        assert response.data["failed"][0]["code"] == "INVALID_TRANSITION"

    def test_bulk_ignores_orders_from_other_stores(
        self, shop, auth, make_user, make_store
    ):
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")
        other_product = Product.objects.create(
            store=other_store, name="Cable", selling_price=Decimal("200")
        )
        receive_stock(get_or_create_stock_item(other_product, None), 10)
        other_customer = Customer.objects.create(
            store=other_store, name="Rahim", phone="01812345678"
        )
        foreign = create_order(
            other_store,
            customer=other_customer,
            items=[{"product": other_product, "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "X"},
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            "/api/v1/orders/bulk-status/",
            {"order_ids": [foreign.id], "status": "confirmed"},
            format="json",
        )

        assert response.data["failed_count"] == 1
        assert response.data["failed"][0]["code"] == "NOT_FOUND"
        foreign.refresh_from_db()
        assert foreign.status == OrderStatus.PENDING


class TestDuplicateCheckEndpoint:
    def test_reports_existing_open_order(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            "/api/v1/orders/check-duplicate/",
            {"phone": "01712345678", "product_ids": [shop["product"].id]},
            format="json",
        )

        assert response.status_code == 200
        assert len(response.data["duplicates"]) == 1
        assert response.data["duplicates"][0]["order_number"] == order.order_number

    def test_unknown_phone_returns_empty(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            "/api/v1/orders/check-duplicate/",
            {"phone": "01999999999"},
            format="json",
        )
        assert response.data["duplicates"] == []


class TestCostVisibility:
    def test_owner_sees_unit_cost(self, shop, auth):
        order = seed_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{ORDERS}{order.id}/"
        )
        assert "unit_cost" in response.data["items"][0]

    def test_order_staff_cannot_see_cost(
        self, shop, auth, make_user, make_member
    ):
        order = seed_order(shop)
        staff = make_user(email="staff@example.com")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=shop["store"]).get(f"{ORDERS}{order.id}/")

        assert response.status_code == 200
        item = response.data["items"][0]
        assert "unit_cost" not in item
        assert "line_margin" not in item


class TestOrderPermissions:
    def test_delivery_staff_cannot_create_orders(
        self, shop, auth, make_user, make_member
    ):
        rider = make_user(email="rider@example.com")
        make_member(shop["store"], rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=shop["store"]).post(
            ORDERS, order_payload(shop), format="json"
        )
        assert response.status_code == 403

    def test_delivery_staff_can_view_orders(
        self, shop, auth, make_user, make_member
    ):
        seed_order(shop)
        rider = make_user(email="rider@example.com")
        make_member(shop["store"], rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=shop["store"]).get(ORDERS)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_accountant_cannot_change_status(
        self, shop, auth, make_user, make_member
    ):
        order = seed_order(shop)
        accountant = make_user(email="acc@example.com")
        make_member(shop["store"], accountant, StoreRole.ACCOUNTANT)

        response = auth(accountant, store=shop["store"]).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "confirmed"},
            format="json",
        )
        assert response.status_code == 403


class TestOrderApiTenancy:
    def test_list_is_scoped(self, shop, auth, make_user, make_store):
        seed_order(shop)

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).get(ORDERS)
        assert response.data["results"] == []

    def test_cannot_read_another_stores_order(
        self, shop, auth, make_user, make_store
    ):
        order = seed_order(shop)

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).get(
            f"{ORDERS}{order.id}/"
        )
        assert response.status_code == 404

    def test_cannot_change_another_stores_order_status(
        self, shop, auth, make_user, make_store
    ):
        order = seed_order(shop)

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).patch(
            f"{ORDERS}{order.id}/status/",
            {"status": "cancelled", "reason": "fake_order"},
            format="json",
        )

        assert response.status_code == 404
        order.refresh_from_db()
        assert order.status == OrderStatus.PENDING
