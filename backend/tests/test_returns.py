from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer, RiskLevel
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.payments.models import Payment, PaymentDirection, PaymentMethod
from apps.payments.services import record_payment
from apps.returns.models import (
    ItemCondition,
    Return,
    ReturnReason,
    ReturnStatus,
    ReturnType,
)
from apps.returns.services import (
    ReturnError,
    create_return,
    receive_return,
    resolve_return,
    return_analytics,
)
from apps.shipments.services import book_shipment

pytestmark = pytest.mark.django_db


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


_counter = {"n": 0}


def delivered_order(shop, quantity=2):
    _counter["n"] += 1
    order = create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )
    order = transition_status(order, OrderStatus.CONFIRMED)
    book_shipment(
        order, shop["courier"], actor=shop["owner"],
        manual_consignment_id=f"CN-{_counter['n']:04d}",
    )
    order.refresh_from_db()
    return transition_status(order, OrderStatus.DELIVERED)


def stock_of(shop):
    item = get_or_create_stock_item(shop["product"], None)
    item.refresh_from_db()
    return item


class TestReturnCreation:
    def test_full_return_defaults_to_all_items(self, shop):
        order = delivered_order(shop, quantity=2)
        record = create_return(
            shop["store"], order,
            reason=ReturnReason.CUSTOMER_REFUSED, actor=shop["owner"],
        )

        assert record.return_type == ReturnType.FULL
        assert record.items.count() == 1
        assert record.items.first().quantity == 2

    def test_partial_return_is_detected(self, shop):
        order = delivered_order(shop, quantity=3)
        item = order.items.first()

        record = create_return(
            shop["store"], order,
            reason=ReturnReason.SIZE_ISSUE,
            items=[{"order_item": item, "quantity": 1}],
        )

        assert record.return_type == ReturnType.PARTIAL

    def test_return_moves_the_order(self, shop):
        order = delivered_order(shop)
        create_return(shop["store"], order, reason=ReturnReason.DAMAGED)
        order.refresh_from_db()

        assert order.status == OrderStatus.RETURNED

    def test_forward_delivery_cost_is_booked(self, shop):
        order = delivered_order(shop)
        record = create_return(
            shop["store"], order, reason=ReturnReason.CUSTOMER_REFUSED,
            return_charge=Decimal("60.00"),
        )

        assert record.forward_delivery_cost > 0
        assert record.return_charge == Decimal("60.00")
        assert record.total_loss >= Decimal("60.00")

    def test_cannot_return_a_pending_order(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        with pytest.raises(ReturnError) as exc:
            create_return(
                shop["store"], order, reason=ReturnReason.DAMAGED
            )
        assert exc.value.code == "ORDER_NOT_RETURNABLE"

    def test_cannot_open_two_returns_for_one_order(self, shop):
        order = delivered_order(shop)
        create_return(shop["store"], order, reason=ReturnReason.DAMAGED)
        order.refresh_from_db()

        with pytest.raises(ReturnError) as exc:
            create_return(
                shop["store"], order, reason=ReturnReason.WRONG_ITEM
            )
        assert exc.value.code == "RETURN_ALREADY_OPEN"

    def test_cannot_return_more_than_ordered(self, shop):
        order = delivered_order(shop, quantity=2)
        item = order.items.first()

        with pytest.raises(ReturnError) as exc:
            create_return(
                shop["store"], order, reason=ReturnReason.DAMAGED,
                items=[{"order_item": item, "quantity": 5}],
            )
        assert exc.value.code == "QUANTITY_EXCEEDS_ORDER"

    def test_order_from_another_store_rejected(
        self, shop, make_user, make_store
    ):
        order = delivered_order(shop)
        stranger = make_store(make_user(email="bob@example.com"), name="Bob")

        with pytest.raises(ReturnError) as exc:
            create_return(stranger, order, reason=ReturnReason.DAMAGED)
        assert exc.value.code == "ORDER_NOT_FOUND"

    def test_return_clears_expected_cod(self, shop):
        from apps.shipments.models import CodStatus

        order = delivered_order(shop)
        record = create_return(
            shop["store"], order, reason=ReturnReason.CUSTOMER_REFUSED
        )

        record.shipment.refresh_from_db()
        assert record.shipment.cod_status == CodStatus.NOT_APPLICABLE


class TestReturnResolution:
    def test_sellable_items_are_restocked(self, shop):
        order = delivered_order(shop, quantity=2)
        before = stock_of(shop).on_hand

        record = create_return(
            shop["store"], order, reason=ReturnReason.SIZE_ISSUE
        )
        receive_return(record)
        resolve_return(record, actor=shop["owner"])

        assert stock_of(shop).on_hand == before + 2

    def test_damaged_items_are_written_off(self, shop):
        order = delivered_order(shop, quantity=2)
        before = stock_of(shop).on_hand

        record = create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED
        )
        receive_return(record)
        return_item = record.items.first()
        record = resolve_return(
            record,
            item_dispositions=[{
                "return_item": return_item.id,
                "condition": ItemCondition.DAMAGED,
                "restock": False,
            }],
            actor=shop["owner"],
        )

        assert stock_of(shop).on_hand == before
        assert record.written_off_value == Decimal("1400.00")

    def test_written_off_value_uses_cost_not_price(self, shop):
        order = delivered_order(shop, quantity=1)
        record = create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED
        )
        receive_return(record)
        record = resolve_return(
            record,
            item_dispositions=[{
                "return_item": record.items.first().id,
                "condition": ItemCondition.DAMAGED,
                "restock": False,
            }],
        )

        assert record.written_off_value == Decimal("700.00")

    def test_refund_creates_an_outgoing_payment(self, shop):
        order = delivered_order(shop, quantity=1)
        record_payment(
            shop["store"], amount=Decimal("500.00"),
            method=PaymentMethod.BKASH, order=order,
        )
        order.refresh_from_db()

        record = create_return(
            shop["store"], order, reason=ReturnReason.CUSTOMER_REFUSED
        )
        receive_return(record)
        resolve_return(
            record, refund_amount=Decimal("500.00"),
            refund_method=PaymentMethod.BKASH, actor=shop["owner"],
        )

        refund = Payment.objects.get(
            order=order, direction=PaymentDirection.OUT
        )
        assert refund.amount == Decimal("500.00")

    def test_refund_cannot_exceed_what_was_paid(self, shop):
        order = delivered_order(shop, quantity=1)
        record_payment(
            shop["store"], amount=Decimal("200.00"),
            method=PaymentMethod.BKASH, order=order,
        )
        order.refresh_from_db()

        record = create_return(
            shop["store"], order, reason=ReturnReason.CUSTOMER_REFUSED
        )
        receive_return(record)

        with pytest.raises(ReturnError) as exc:
            resolve_return(record, refund_amount=Decimal("5000.00"))
        assert exc.value.code == "REFUND_EXCEEDS_PAID"

    def test_resolve_marks_status_and_timestamp(self, shop):
        order = delivered_order(shop)
        record = create_return(
            shop["store"], order, reason=ReturnReason.SIZE_ISSUE
        )
        receive_return(record)
        record = resolve_return(record, resolution_note="Restocked")

        assert record.status == ReturnStatus.RESOLVED
        assert record.resolved_at is not None
        assert record.resolution_note == "Restocked"

    def test_double_resolve_is_rejected(self, shop):
        order = delivered_order(shop)
        record = create_return(
            shop["store"], order, reason=ReturnReason.SIZE_ISSUE
        )
        receive_return(record)
        resolve_return(record)
        record.refresh_from_db()

        with pytest.raises(ReturnError) as exc:
            resolve_return(record)
        assert exc.value.code == "RETURN_ALREADY_RESOLVED"

    def test_receive_requires_initiated_status(self, shop):
        order = delivered_order(shop)
        record = create_return(
            shop["store"], order, reason=ReturnReason.SIZE_ISSUE
        )
        receive_return(record)
        record.refresh_from_db()

        with pytest.raises(ReturnError) as exc:
            receive_return(record)
        assert exc.value.code == "RETURN_NOT_INITIATED"


class TestCustomerImpact:
    def test_return_escalates_customer_risk(self, shop):
        order = delivered_order(shop)
        create_return(shop["store"], order, reason=ReturnReason.FAKE_ORDER)

        shop["customer"].refresh_from_db()
        assert shop["customer"].returned_count == 1
        assert shop["customer"].risk_level == RiskLevel.HIGH_RISK


class TestReturnAnalytics:
    def test_counts_returns_and_rate(self, shop):
        delivered_order(shop)
        order = delivered_order(shop)
        create_return(shop["store"], order, reason=ReturnReason.DAMAGED)

        data = return_analytics(shop["store"])

        assert data["total_returns"] == 1
        assert data["shipped_orders"] == 2
        assert data["return_rate"] == Decimal("50.00")

    def test_groups_by_reason(self, shop):
        for reason in (ReturnReason.DAMAGED, ReturnReason.SIZE_ISSUE):
            order = delivered_order(shop)
            create_return(shop["store"], order, reason=reason)

        data = return_analytics(shop["store"])
        reasons = {r["reason"] for r in data["by_reason"]}

        assert reasons == {ReturnReason.DAMAGED, ReturnReason.SIZE_ISSUE}

    def test_totals_the_loss(self, shop):
        order = delivered_order(shop)
        create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED,
            return_charge=Decimal("60.00"),
        )

        data = return_analytics(shop["store"])
        assert data["total_loss"] > Decimal("0.00")

    def test_groups_by_product(self, shop):
        order = delivered_order(shop, quantity=2)
        create_return(shop["store"], order, reason=ReturnReason.DAMAGED)

        data = return_analytics(shop["store"])
        assert data["by_product"][0]["order_item__product_name"] == "Cotton Kurti"
        assert data["by_product"][0]["quantity"] == 2

    def test_empty_store_does_not_divide_by_zero(
        self, shop, make_user, make_store
    ):
        stranger = make_store(make_user(email="bob@example.com"), name="Bob")
        data = return_analytics(stranger)

        assert data["total_returns"] == 0
        assert data["return_rate"] == Decimal("0.00")


class TestReturnTenancy:
    def test_returns_are_scoped(self, shop, make_user, make_store):
        order = delivered_order(shop)
        create_return(shop["store"], order, reason=ReturnReason.DAMAGED)

        stranger = make_store(make_user(email="bob@example.com"), name="Bob")

        assert Return.objects.for_store(shop["store"]).count() == 1
        assert Return.objects.for_store(stranger).count() == 0
