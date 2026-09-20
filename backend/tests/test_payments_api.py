import io
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.expenses.models import Expense, ExpenseCategory
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.payments.models import SettlementStatus
from apps.returns.models import ReturnReason, ReturnStatus
from apps.returns.services import create_return
from apps.shipments.models import CodStatus
from apps.shipments.services import book_shipment
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

PAYMENTS = "/api/v1/payments/"
SETTLEMENTS = "/api/v1/payments/settlements/"
LEDGER = "/api/v1/payments/cod-ledger/"
RETURNS = "/api/v1/returns/"
EXPENSES = "/api/v1/expenses/"


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti",
        selling_price=Decimal("1200.00"), cost_price=Decimal("700.00"),
    )
    receive_stock(get_or_create_stock_item(product, None), 100)
    customer = Customer.objects.create(
        store=store, name="Karim Ahmed", phone="01712345678"
    )
    courier = StoreCourier.objects.create(
        store=store, courier=Courier.objects.get(code="manual"),
        is_default=True,
    )
    return {
        "owner": owner, "store": store, "product": product,
        "customer": customer, "courier": courier,
    }


_n = {"i": 0}


def delivered_order(shop, quantity=1):
    _n["i"] += 1
    order = create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )
    order = transition_status(order, OrderStatus.CONFIRMED)
    shipment = book_shipment(
        order, shop["courier"], actor=shop["owner"],
        manual_consignment_id=f"CN-{_n['i']:04d}",
    )
    shipment.delivered_at = timezone.now()
    shipment.cod_status = CodStatus.COLLECTED
    shipment.save()
    order.refresh_from_db()
    order = transition_status(order, OrderStatus.DELIVERED)
    return order, shipment


class TestPaymentEndpoint:
    def test_records_an_advance(self, shop, auth):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            PAYMENTS,
            {"order": order.id, "method": "bkash", "amount": "500.00",
             "reference": "TRX123"},
            format="json",
        )

        assert response.status_code == 201
        order.refresh_from_db()
        assert order.advance_paid == Decimal("500.00")

    def test_rejects_zero_amount(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            PAYMENTS, {"method": "cash", "amount": "0"}, format="json"
        )
        assert response.status_code == 400

    def test_rejects_order_from_another_store(
        self, shop, auth, make_user, make_store
    ):
        order, _ = delivered_order(shop)
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).post(
            PAYMENTS,
            {"order": order.id, "method": "cash", "amount": "100"},
            format="json",
        )
        assert response.status_code == 400

    def test_order_staff_cannot_record_payments(
        self, shop, auth, make_user, make_member
    ):
        staff = make_user(email="staff@example.com")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=shop["store"]).post(
            PAYMENTS, {"method": "cash", "amount": "100"}, format="json"
        )
        assert response.status_code == 403

    def test_accountant_can_record_payments(
        self, shop, auth, make_user, make_member
    ):
        accountant = make_user(email="acc@example.com")
        make_member(shop["store"], accountant, StoreRole.ACCOUNTANT)

        response = auth(accountant, store=shop["store"]).post(
            PAYMENTS, {"method": "cash", "amount": "100"}, format="json"
        )
        assert response.status_code == 201


class TestSettlementEndpoint:
    def _csv(self, body):
        upload = io.BytesIO(body.encode("utf-8"))
        upload.name = "statement.csv"
        return upload

    def test_upload_creates_a_draft(self, shop, auth):
        order, shipment = delivered_order(shop)
        upload = self._csv(
            "consignment_id,amount,charge\n"
            f"{shipment.consignment_id},{order.cod_amount},70\n"
        )

        response = auth(shop["owner"], store=shop["store"]).post(
            SETTLEMENTS,
            {"store_courier": shop["courier"].id, "file": upload,
             "statement_reference": "STMT-1"},
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["status"] == SettlementStatus.DRAFT
        assert response.data["matched_count"] == 1

    def test_upload_does_not_settle_anything(self, shop, auth):
        order, shipment = delivered_order(shop)
        upload = self._csv(
            "consignment_id,amount,charge\n"
            f"{shipment.consignment_id},{order.cod_amount},70\n"
        )

        auth(shop["owner"], store=shop["store"]).post(
            SETTLEMENTS,
            {"store_courier": shop["courier"].id, "file": upload},
            format="multipart",
        )

        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.COLLECTED

    def test_preview_buckets_the_rows(self, shop, auth):
        order, shipment = delivered_order(shop)
        upload = self._csv(
            "consignment_id,amount,charge\n"
            f"{shipment.consignment_id},{order.cod_amount},70\n"
            "GHOST-1,500,50\n"
        )

        client = auth(shop["owner"], store=shop["store"])
        created = client.post(
            SETTLEMENTS,
            {"store_courier": shop["courier"].id, "file": upload},
            format="multipart",
        )
        response = client.get(f"{SETTLEMENTS}{created.data['id']}/preview/")

        assert response.status_code == 200
        assert response.data["counts"]["matched"] == 1
        assert response.data["counts"]["unmatched"] == 1

    def test_commit_settles_matched_rows(self, shop, auth):
        order, shipment = delivered_order(shop)
        upload = self._csv(
            "consignment_id,amount,charge\n"
            f"{shipment.consignment_id},{order.cod_amount},70\n"
        )

        client = auth(shop["owner"], store=shop["store"])
        created = client.post(
            SETTLEMENTS,
            {"store_courier": shop["courier"].id, "file": upload},
            format="multipart",
        )
        response = client.post(
            f"{SETTLEMENTS}{created.data['id']}/commit/", {}, format="json"
        )

        assert response.status_code == 200
        assert response.data["settled_count"] == 1
        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.SETTLED

    def test_non_utf8_file_is_rejected(self, shop, auth):
        upload = io.BytesIO(b"\xff\xfe\x00bad")
        upload.name = "bad.csv"

        response = auth(shop["owner"], store=shop["store"]).post(
            SETTLEMENTS,
            {"store_courier": shop["courier"].id, "file": upload},
            format="multipart",
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "INVALID_ENCODING"

    def test_order_staff_cannot_reconcile(
        self, shop, auth, make_user, make_member
    ):
        staff = make_user(email="staff@example.com")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=shop["store"]).get(SETTLEMENTS)
        assert response.status_code == 403


class TestCodLedgerEndpoint:
    def test_returns_the_buckets(self, shop, auth):
        delivered_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(LEDGER)

        assert response.status_code == 200
        assert response.data["collected_unsettled"]["count"] == 1
        assert "overdue" in response.data
        assert "shortfalls" in response.data

    def test_overdue_days_can_be_overridden(self, shop, auth):
        delivered_order(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{LEDGER}?overdue_days=0"
        )
        assert response.data["overdue_days"] == 0


class TestReturnEndpoint:
    def test_creates_a_return(self, shop, auth):
        order, _ = delivered_order(shop, quantity=2)

        response = auth(shop["owner"], store=shop["store"]).post(
            RETURNS,
            {"order": order.id, "reason": "damaged",
             "reason_note": "Torn on arrival", "return_charge": "60.00"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["status"] == ReturnStatus.INITIATED
        assert len(response.data["items"]) == 1

    def test_receive_then_resolve(self, shop, auth):
        order, _ = delivered_order(shop, quantity=2)
        client = auth(shop["owner"], store=shop["store"])

        created = client.post(
            RETURNS, {"order": order.id, "reason": "size_issue"},
            format="json",
        )
        rid = created.data["id"]

        received = client.post(f"{RETURNS}{rid}/receive/", {}, format="json")
        assert received.data["status"] == ReturnStatus.RECEIVED

        resolved = client.post(
            f"{RETURNS}{rid}/resolve/",
            {"resolution_note": "Back in stock"},
            format="json",
        )
        assert resolved.data["status"] == ReturnStatus.RESOLVED

    def test_resolve_restocks_sellable_items(self, shop, auth):
        order, _ = delivered_order(shop, quantity=2)
        item = get_or_create_stock_item(shop["product"], None)
        item.refresh_from_db()
        before = item.on_hand

        client = auth(shop["owner"], store=shop["store"])
        created = client.post(
            RETURNS, {"order": order.id, "reason": "size_issue"},
            format="json",
        )
        client.post(f"{RETURNS}{created.data['id']}/receive/", {}, format="json")
        client.post(
            f"{RETURNS}{created.data['id']}/resolve/", {}, format="json"
        )

        item.refresh_from_db()
        assert item.on_hand == before + 2

    def test_invalid_item_is_rejected(self, shop, auth):
        order, _ = delivered_order(shop)

        response = auth(shop["owner"], store=shop["store"]).post(
            RETURNS,
            {
                "order": order.id, "reason": "damaged",
                "items": [{"order_item": 999999, "quantity": 1}],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_delivery_staff_can_record_returns(
        self, shop, auth, make_user, make_member
    ):
        order, _ = delivered_order(shop)
        rider = make_user(email="rider@example.com")
        make_member(shop["store"], rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=shop["store"]).post(
            RETURNS, {"order": order.id, "reason": "customer_refused"},
            format="json",
        )
        assert response.status_code == 201

    def test_cannot_return_another_stores_order(
        self, shop, auth, make_user, make_store
    ):
        order, _ = delivered_order(shop)
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).post(
            RETURNS, {"order": order.id, "reason": "damaged"}, format="json"
        )
        assert response.status_code == 400

    def test_analytics_endpoint(self, shop, auth):
        order, _ = delivered_order(shop)
        create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED
        )

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{RETURNS}analytics/"
        )

        assert response.status_code == 200
        assert response.data["total_returns"] == 1
        assert "by_reason" in response.data


class TestExpenseEndpoint:
    def test_creates_an_expense(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            EXPENSES,
            {"date": str(date.today()), "category": "ad_spend",
             "amount": "2500.00", "note": "Facebook boost"},
            format="json",
        )

        assert response.status_code == 201
        assert Expense.objects.filter(store=shop["store"]).count() == 1

    def test_rejects_zero_amount(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            EXPENSES,
            {"date": str(date.today()), "category": "rent", "amount": "0"},
            format="json",
        )
        assert response.status_code == 400

    def test_summary_groups_by_category(self, shop, auth):
        client = auth(shop["owner"], store=shop["store"])
        for category, amount in (
            (ExpenseCategory.AD_SPEND, "1000"),
            (ExpenseCategory.AD_SPEND, "500"),
            (ExpenseCategory.RENT, "8000"),
        ):
            client.post(
                EXPENSES,
                {"date": str(date.today()), "category": category,
                 "amount": amount},
                format="json",
            )

        response = client.get(f"{EXPENSES}summary/")

        assert Decimal(response.data["total"]) == Decimal("9500")
        top = response.data["by_category"][0]
        assert top["category"] == ExpenseCategory.RENT

    def test_order_staff_cannot_see_expenses(
        self, shop, auth, make_user, make_member
    ):
        staff = make_user(email="staff@example.com")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=shop["store"]).get(EXPENSES)
        assert response.status_code == 403

    def test_expenses_are_scoped_to_the_store(
        self, shop, auth, make_user, make_store
    ):
        Expense.objects.create(
            store=shop["store"], date=date.today(),
            category=ExpenseCategory.RENT, amount=Decimal("8000"),
        )
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other_store).get(EXPENSES)
        assert response.data["results"] == []
