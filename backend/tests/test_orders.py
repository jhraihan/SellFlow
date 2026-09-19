from decimal import Decimal

import pytest

from apps.catalog.models import Product, ProductVariant
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.core.exceptions import InsufficientStock, InvalidTransition
from apps.customers.models import Customer, RiskLevel
from apps.orders.models import (
    LEGAL_TRANSITIONS,
    CallOutcome,
    Order,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
)
from apps.orders.services import (
    OrderError,
    OrderNotEditable,
    create_order,
    find_duplicate_orders,
    log_call,
    set_advance_payment,
    transition_status,
    update_items,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    return {"owner": owner, "store": store}


@pytest.fixture
def product(shop):
    p = Product.objects.create(
        store=shop["store"],
        name="Cotton Kurti",
        selling_price=Decimal("1200.00"),
        cost_price=Decimal("700.00"),
    )
    item = get_or_create_stock_item(p, None)
    receive_stock(item, 50)
    return p


@pytest.fixture
def customer(shop):
    return Customer.objects.create(
        store=shop["store"], name="Karim Ahmed", phone="01712345678"
    )


def _shipping(**overrides):
    data = {
        "district": "Dhaka",
        "thana": "Dhanmondi",
        "address_line": "House 12, Road 4",
    }
    data.update(overrides)
    return data


def make_order(shop, customer, product, quantity=2, **kwargs):
    return create_order(
        shop["store"],
        customer=customer,
        items=[{"product": product, "quantity": quantity}],
        shipping=_shipping(),
        actor=shop["owner"],
        **kwargs,
    )


class TestOrderCreation:
    def test_creates_order_with_computed_totals(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=2)

        assert order.subtotal == Decimal("2400.00")
        assert order.delivery_charge == Decimal("60.00")
        assert order.total_amount == Decimal("2460.00")
        assert order.cod_amount == Decimal("2460.00")
        assert order.status == OrderStatus.PENDING

    def test_discount_and_advance_affect_cod(self, shop, customer, product):
        order = make_order(
            shop, customer, product, quantity=2,
            discount_amount=Decimal("100.00"),
            advance_paid=Decimal("500.00"),
        )

        assert order.total_amount == Decimal("2360.00")
        assert order.cod_amount == Decimal("1860.00")
        assert order.payment_status == PaymentStatus.PARTIALLY_PAID

    def test_full_advance_marks_order_paid(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=1)
        order = set_advance_payment(order, order.total_amount)

        assert order.cod_amount == Decimal("0.00")
        assert order.payment_status == PaymentStatus.PAID

    def test_outside_dhaka_uses_higher_delivery_charge(
        self, shop, customer, product
    ):
        order = create_order(
            shop["store"],
            customer=customer,
            items=[{"product": product, "quantity": 1}],
            shipping=_shipping(district="Sylhet"),
            actor=shop["owner"],
        )

        assert order.delivery_charge == Decimal("120.00")

    def test_free_delivery_threshold_applies(self, shop, customer, product):
        settings = shop["store"].settings
        settings.free_delivery_threshold = Decimal("2000.00")
        settings.save()

        order = make_order(shop, customer, product, quantity=2)

        assert order.delivery_charge == Decimal("0.00")
        assert order.total_amount == Decimal("2400.00")

    def test_order_numbers_are_sequential_per_store(
        self, shop, customer, product
    ):
        first = make_order(shop, customer, product)
        second = make_order(shop, customer, product)

        assert first.order_number == "ORD-1001"
        assert second.order_number == "ORD-1002"

    def test_order_number_uses_store_prefix(self, shop, customer, product):
        store = shop["store"]
        store.order_prefix = "RB"
        store.save()

        order = make_order(shop, customer, product)
        assert order.order_number.startswith("RB-")

    def test_rejects_empty_item_list(self, shop, customer):
        with pytest.raises(OrderError):
            create_order(
                shop["store"],
                customer=customer,
                items=[],
                shipping=_shipping(),
            )

    def test_rejects_discount_larger_than_subtotal(
        self, shop, customer, product
    ):
        with pytest.raises(OrderError) as exc:
            make_order(
                shop, customer, product, quantity=1,
                discount_amount=Decimal("9999.00"),
            )
        assert exc.value.code == "DISCOUNT_TOO_LARGE"

    def test_rejects_advance_larger_than_total(self, shop, customer, product):
        with pytest.raises(OrderError) as exc:
            make_order(
                shop, customer, product, quantity=1,
                advance_paid=Decimal("99999.00"),
            )
        assert exc.value.code == "ADVANCE_TOO_LARGE"

    def test_rejects_product_from_another_store(
        self, shop, customer, make_user, make_store
    ):
        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")
        foreign = Product.objects.create(
            store=other_store, name="Bob Cable", selling_price=Decimal("200")
        )

        with pytest.raises(OrderError) as exc:
            create_order(
                shop["store"],
                customer=customer,
                items=[{"product": foreign, "quantity": 1}],
                shipping=_shipping(),
            )
        assert exc.value.code == "UNKNOWN_PRODUCT"

    def test_writes_creation_history_row(self, shop, customer, product):
        order = make_order(shop, customer, product)
        history = OrderStatusHistory.objects.filter(order=order)

        assert history.count() == 1
        assert history.first().to_status == OrderStatus.PENDING

    def test_creation_bumps_customer_order_count(
        self, shop, customer, product
    ):
        make_order(shop, customer, product)
        customer.refresh_from_db()

        assert customer.total_orders == 1
        assert customer.last_order_at is not None


class TestPriceSnapshots:
    def test_item_snapshots_name_price_and_cost(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=2)
        item = order.items.first()

        assert item.product_name == "Cotton Kurti"
        assert item.unit_price == Decimal("1200.00")
        assert item.unit_cost == Decimal("700.00")
        assert item.line_total == Decimal("2400.00")

    def test_later_product_edits_do_not_change_past_orders(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=2)

        product.name = "Renamed Kurti"
        product.selling_price = Decimal("1500.00")
        product.cost_price = Decimal("900.00")
        product.save()

        item = order.items.first()
        order.refresh_from_db()

        assert item.product_name == "Cotton Kurti"
        assert item.unit_price == Decimal("1200.00")
        assert item.unit_cost == Decimal("700.00")
        assert order.subtotal == Decimal("2400.00")

    def test_variant_snapshot_records_label_and_override_price(
        self, shop, customer
    ):
        store = shop["store"]
        parent = Product.objects.create(
            store=store, name="T-Shirt",
            selling_price=Decimal("550.00"), has_variants=True,
        )
        variant = ProductVariant.objects.create(
            store=store, product=parent,
            option1_name="Size", option1_value="XL",
            price_override=Decimal("650.00"),
        )
        item_stock = get_or_create_stock_item(parent, variant)
        receive_stock(item_stock, 10)

        order = create_order(
            store,
            customer=customer,
            items=[{"product": parent, "variant": variant, "quantity": 1}],
            shipping=_shipping(),
        )
        item = order.items.first()

        assert item.variant_label == "XL"
        assert item.unit_price == Decimal("650.00")

    def test_variant_required_when_product_has_variants(self, shop, customer):
        store = shop["store"]
        parent = Product.objects.create(
            store=store, name="T-Shirt",
            selling_price=Decimal("550.00"), has_variants=True,
        )

        with pytest.raises(OrderError) as exc:
            create_order(
                store,
                customer=customer,
                items=[{"product": parent, "quantity": 1}],
                shipping=_shipping(),
            )
        assert exc.value.code == "VARIANT_REQUIRED"


class TestStateMachine:
    def test_legal_transition_succeeds(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = transition_status(
            order, OrderStatus.CONFIRMED, actor=shop["owner"]
        )

        assert order.status == OrderStatus.CONFIRMED
        assert order.confirmed_at is not None

    @pytest.mark.parametrize(
        "target",
        [
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.RETURNED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.PROCESSING,
        ],
    )
    def test_illegal_jump_from_pending_is_rejected(
        self, shop, customer, product, target
    ):
        order = make_order(shop, customer, product)

        with pytest.raises(InvalidTransition):
            transition_status(order, target)

        order.refresh_from_db()
        assert order.status == OrderStatus.PENDING

    def test_cannot_transition_to_current_status(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product)

        with pytest.raises(InvalidTransition):
            transition_status(order, OrderStatus.PENDING)

    def test_cancelled_is_terminal(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = transition_status(
            order, OrderStatus.CANCELLED, reason="customer_cancelled"
        )

        for target in OrderStatus.values:
            if target == OrderStatus.CANCELLED:
                continue
            with pytest.raises(InvalidTransition):
                transition_status(order, target)

    def test_returned_is_terminal(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = transition_status(order, OrderStatus.CONFIRMED)
        order = transition_status(order, OrderStatus.READY_TO_SHIP)
        order = transition_status(order, OrderStatus.SHIPPED)
        order = transition_status(order, OrderStatus.RETURNED)

        for target in OrderStatus.values:
            if target == OrderStatus.RETURNED:
                continue
            with pytest.raises(InvalidTransition):
                transition_status(order, target)

    def test_delivered_may_still_be_returned(self, shop, customer, product):
        order = make_order(shop, customer, product)
        for target in (
            OrderStatus.CONFIRMED,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = transition_status(order, target)

        order = transition_status(order, OrderStatus.RETURNED)
        assert order.status == OrderStatus.RETURNED

    def test_on_hold_can_return_to_pending(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = transition_status(order, OrderStatus.ON_HOLD)
        order = transition_status(order, OrderStatus.PENDING)

        assert order.status == OrderStatus.PENDING

    def test_every_transition_writes_history(self, shop, customer, product):
        order = make_order(shop, customer, product)
        transition_status(order, OrderStatus.CONFIRMED, note="Called customer")
        order.refresh_from_db()
        transition_status(order, OrderStatus.READY_TO_SHIP)

        history = list(OrderStatusHistory.objects.filter(order=order))
        assert [h.to_status for h in history] == [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.READY_TO_SHIP,
        ]
        assert history[1].note == "Called customer"

    def test_history_is_immutable(self, shop, customer, product):
        order = make_order(shop, customer, product)
        row = OrderStatusHistory.objects.filter(order=order).first()

        row.note = "tampered"
        with pytest.raises(ValueError):
            row.save()
        with pytest.raises(ValueError):
            row.delete()

    def test_cancel_requires_a_reason(self, shop, customer, product):
        order = make_order(shop, customer, product)

        with pytest.raises(OrderError) as exc:
            transition_status(order, OrderStatus.CANCELLED)
        assert exc.value.code == "CANCEL_REASON_REQUIRED"

    def test_transition_map_has_no_unknown_statuses(self):
        valid = set(OrderStatus.values)
        for source, targets in LEGAL_TRANSITIONS.items():
            assert source in valid
            assert set(targets) <= valid


class TestStockSideEffects:
    def _stock(self, product):
        item = get_or_create_stock_item(product, None)
        item.refresh_from_db()
        return item

    def test_confirming_reserves_stock(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=3)
        transition_status(order, OrderStatus.CONFIRMED)

        stock = self._stock(product)
        assert stock.on_hand == 50
        assert stock.reserved == 3
        assert stock.available == 47

    def test_pending_order_reserves_nothing(self, shop, customer, product):
        make_order(shop, customer, product, quantity=3)

        stock = self._stock(product)
        assert stock.reserved == 0

    def test_cancelling_releases_reservation(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=3)
        order = transition_status(order, OrderStatus.CONFIRMED)
        transition_status(order, OrderStatus.CANCELLED, reason="out_of_stock")

        stock = self._stock(product)
        assert stock.reserved == 0
        assert stock.on_hand == 50

    def test_shipping_decrements_on_hand_and_clears_reservation(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=3)
        order = transition_status(order, OrderStatus.CONFIRMED)
        order = transition_status(order, OrderStatus.READY_TO_SHIP)
        transition_status(order, OrderStatus.SHIPPED)

        stock = self._stock(product)
        assert stock.on_hand == 47
        assert stock.reserved == 0

    def test_cannot_confirm_without_enough_stock(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=80)

        with pytest.raises(InsufficientStock):
            transition_status(order, OrderStatus.CONFIRMED)

        order.refresh_from_db()
        assert order.status == OrderStatus.PENDING
        assert self._stock(product).reserved == 0

    def test_holding_a_confirmed_order_releases_stock(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=3)
        order = transition_status(order, OrderStatus.CONFIRMED)
        transition_status(order, OrderStatus.ON_HOLD)

        assert self._stock(product).reserved == 0

    def test_moving_through_processing_keeps_one_reservation(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=3)
        order = transition_status(order, OrderStatus.CONFIRMED)
        order = transition_status(order, OrderStatus.PROCESSING)
        transition_status(order, OrderStatus.READY_TO_SHIP)

        stock = self._stock(product)
        assert stock.reserved == 3


class TestConfirmationWorkflow:
    def test_confirmed_call_confirms_the_order(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = log_call(order, CallOutcome.CONFIRMED, actor=shop["owner"])

        assert order.status == OrderStatus.CONFIRMED
        assert order.confirmation_attempts == 1

    def test_no_answer_only_increments_the_counter(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product)
        order = log_call(order, CallOutcome.NO_ANSWER)
        order.refresh_from_db()

        assert order.status == OrderStatus.PENDING
        assert order.confirmation_attempts == 1
        assert order.last_call_outcome == CallOutcome.NO_ANSWER

    def test_repeated_calls_accumulate(self, shop, customer, product):
        order = make_order(shop, customer, product)
        log_call(order, CallOutcome.NO_ANSWER)
        order.refresh_from_db()
        log_call(order, CallOutcome.CALL_LATER)
        order.refresh_from_db()

        assert order.confirmation_attempts == 2

    def test_fake_call_cancels_the_order(self, shop, customer, product):
        order = make_order(shop, customer, product)
        order = log_call(order, CallOutcome.FAKE)

        assert order.status == OrderStatus.CANCELLED
        assert order.cancel_reason == "fake_order"


class TestOrderEditing:
    def test_items_can_be_changed_while_pending(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=2)
        order = update_items(
            order, [{"product": product, "quantity": 5}], actor=shop["owner"]
        )

        assert order.items.count() == 1
        assert order.items.first().quantity == 5
        assert order.subtotal == Decimal("6000.00")

    def test_editing_a_confirmed_order_rereserves_stock(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product, quantity=2)
        order = transition_status(order, OrderStatus.CONFIRMED)
        update_items(order, [{"product": product, "quantity": 5}])

        stock = get_or_create_stock_item(product, None)
        stock.refresh_from_db()
        assert stock.reserved == 5

    def test_items_are_frozen_once_processing(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=2)
        order = transition_status(order, OrderStatus.CONFIRMED)
        order = transition_status(order, OrderStatus.PROCESSING)

        with pytest.raises(OrderNotEditable):
            update_items(order, [{"product": product, "quantity": 9}])

    def test_items_are_frozen_once_shipped(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=2)
        for target in (
            OrderStatus.CONFIRMED,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
        ):
            order = transition_status(order, target)

        with pytest.raises(OrderNotEditable):
            update_items(order, [{"product": product, "quantity": 9}])


class TestCustomerMetrics:
    def test_delivery_updates_lifetime_value(self, shop, customer, product):
        order = make_order(shop, customer, product, quantity=2)
        for target in (
            OrderStatus.CONFIRMED,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = transition_status(order, target)

        customer.refresh_from_db()
        assert customer.delivered_count == 1
        assert customer.lifetime_value == order.total_amount

    def test_return_updates_return_count_and_risk(
        self, shop, customer, product
    ):
        order = make_order(shop, customer, product)
        for target in (
            OrderStatus.CONFIRMED,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
            OrderStatus.RETURNED,
        ):
            order = transition_status(order, target)

        customer.refresh_from_db()
        assert customer.returned_count == 1
        assert customer.risk_level == RiskLevel.HIGH_RISK

    def test_cancellation_counts_separately(self, shop, customer, product):
        order = make_order(shop, customer, product)
        transition_status(order, OrderStatus.CANCELLED, reason="fake_order")

        customer.refresh_from_db()
        assert customer.cancelled_count == 1
        assert customer.returned_count == 0


class TestDuplicateDetection:
    def test_finds_recent_open_order_with_same_product(
        self, shop, customer, product
    ):
        make_order(shop, customer, product)

        matches = find_duplicate_orders(
            shop["store"], customer, [product.id]
        )
        assert len(matches) == 1

    def test_ignores_cancelled_orders(self, shop, customer, product):
        order = make_order(shop, customer, product)
        transition_status(order, OrderStatus.CANCELLED, reason="duplicate")

        matches = find_duplicate_orders(
            shop["store"], customer, [product.id]
        )
        assert len(matches) == 0

    def test_ignores_unrelated_products(self, shop, customer, product):
        make_order(shop, customer, product)
        other = Product.objects.create(
            store=shop["store"], name="Saree", selling_price=Decimal("2500")
        )

        matches = find_duplicate_orders(shop["store"], customer, [other.id])
        assert len(matches) == 0


class TestOrderTenancy:
    def test_orders_are_scoped_to_their_store(
        self, shop, customer, product, make_user, make_store
    ):
        make_order(shop, customer, product)

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")

        assert Order.objects.for_store(shop["store"]).count() == 1
        assert Order.objects.for_store(other_store).count() == 0

    def test_order_numbers_restart_per_store(
        self, shop, customer, product, make_user, make_store
    ):
        first = make_order(shop, customer, product)

        stranger = make_user(email="bob@example.com")
        other_store = make_store(stranger, name="Bob Store")
        other_product = Product.objects.create(
            store=other_store, name="Cable", selling_price=Decimal("200")
        )
        receive_stock(get_or_create_stock_item(other_product, None), 10)
        other_customer = Customer.objects.create(
            store=other_store, name="Rahim", phone="01812345678"
        )

        second = create_order(
            other_store,
            customer=other_customer,
            items=[{"product": other_product, "quantity": 1}],
            shipping=_shipping(),
        )

        assert first.order_number == "ORD-1001"
        assert second.order_number == "ORD-1001"
