from decimal import Decimal

import pytest

from apps.catalog.models import MovementType, Product, StockMovement
from apps.catalog.services import (
    StockError,
    adjust_stock,
    get_or_create_stock_item,
    rebuild_stock_from_ledger,
    receive_stock,
    release_reservation,
    reserve_stock,
    restock_return,
    ship_stock,
    write_off,
)
from apps.core.exceptions import InsufficientStock

pytestmark = pytest.mark.django_db


@pytest.fixture
def product(make_user, make_store):
    store = make_store(make_user())
    return Product.objects.create(
        store=store,
        name="Cotton Kurti",
        selling_price=Decimal("1200.00"),
        cost_price=Decimal("700.00"),
        low_stock_threshold=5,
    )


@pytest.fixture
def stock(product):
    return get_or_create_stock_item(product, None)


class TestReceiveAndAdjust:
    def test_receive_increases_on_hand(self, stock):
        receive_stock(stock, 50)
        stock.refresh_from_db()

        assert stock.on_hand == 50
        assert stock.reserved == 0
        assert stock.available == 50

    def test_receive_writes_a_movement(self, stock):
        receive_stock(stock, 50, reason="Opening stock")
        movement = StockMovement.objects.get(stock_item=stock)

        assert movement.movement_type == MovementType.PURCHASE
        assert movement.quantity == 50
        assert movement.on_hand_after == 50
        assert movement.reason == "Opening stock"

    def test_receive_rejects_zero_or_negative(self, stock):
        with pytest.raises(StockError):
            receive_stock(stock, 0)
        with pytest.raises(StockError):
            receive_stock(stock, -5)

    def test_adjust_sets_absolute_level(self, stock):
        receive_stock(stock, 50)
        adjust_stock(stock, 42, reason="Stock count")
        stock.refresh_from_db()

        assert stock.on_hand == 42

    def test_adjust_records_the_delta(self, stock):
        receive_stock(stock, 50)
        movement = adjust_stock(stock, 42, reason="Stock count")

        assert movement.quantity == -8
        assert movement.on_hand_after == 42

    def test_adjust_requires_a_reason(self, stock):
        receive_stock(stock, 10)
        with pytest.raises(StockError):
            adjust_stock(stock, 5, reason="")

    def test_adjust_rejects_negative_target(self, stock):
        with pytest.raises(StockError):
            adjust_stock(stock, -1, reason="Typo")

    def test_adjust_to_same_level_is_a_no_op(self, stock):
        receive_stock(stock, 10)
        movement = adjust_stock(stock, 10, reason="No change")

        assert movement is None
        assert StockMovement.objects.filter(stock_item=stock).count() == 1


class TestReservation:
    def test_reserve_does_not_change_on_hand(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 5)
        stock.refresh_from_db()

        assert stock.on_hand == 20
        assert stock.reserved == 5
        assert stock.available == 15

    def test_cannot_reserve_more_than_available(self, stock):
        receive_stock(stock, 10)

        with pytest.raises(InsufficientStock) as exc:
            reserve_stock(stock, 11)

        assert exc.value.details["available"] == 10

    def test_reserving_exactly_available_is_allowed(self, stock):
        receive_stock(stock, 10)
        reserve_stock(stock, 10)
        stock.refresh_from_db()

        assert stock.available == 0

    def test_second_reservation_respects_the_first(self, stock):
        receive_stock(stock, 10)
        reserve_stock(stock, 6)

        with pytest.raises(InsufficientStock):
            reserve_stock(stock, 5)

    def test_release_returns_stock_to_available(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 8)
        release_reservation(stock, 8)
        stock.refresh_from_db()

        assert stock.reserved == 0
        assert stock.available == 20

    def test_cannot_release_more_than_reserved(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 3)

        with pytest.raises(StockError):
            release_reservation(stock, 4)


class TestShipping:
    def test_ship_reduces_on_hand_and_clears_reservation(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 5)
        ship_stock(stock, 5)
        stock.refresh_from_db()

        assert stock.on_hand == 15
        assert stock.reserved == 0
        assert stock.available == 15

    def test_ship_writes_release_then_sale(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 5)
        ship_stock(stock, 5, order_id=99)

        types = list(
            StockMovement.objects.filter(stock_item=stock)
            .order_by("created_at", "id")
            .values_list("movement_type", flat=True)
        )
        assert types == [
            MovementType.PURCHASE,
            MovementType.ORDER_RESERVE,
            MovementType.RESERVE_RELEASE,
            MovementType.SALE,
        ]

    def test_ship_links_to_the_order(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 5, order_id=99)
        ship_stock(stock, 5, order_id=99)

        sale = StockMovement.objects.get(
            stock_item=stock, movement_type=MovementType.SALE
        )
        assert sale.reference_type == "order"
        assert sale.reference_id == 99


class TestReturns:
    def test_restock_adds_stock_back(self, stock):
        receive_stock(stock, 20)
        reserve_stock(stock, 3)
        ship_stock(stock, 3)
        restock_return(stock, 3, return_id=7)
        stock.refresh_from_db()

        assert stock.on_hand == 20

    def test_write_off_removes_stock_without_restocking(self, stock):
        receive_stock(stock, 20)
        write_off(stock, 2, reason="Damaged in transit")
        stock.refresh_from_db()

        assert stock.on_hand == 18

    def test_write_off_requires_a_reason(self, stock):
        receive_stock(stock, 20)
        with pytest.raises(StockError):
            write_off(stock, 2, reason="")


class TestLedgerIntegrity:
    def test_movements_cannot_be_updated(self, stock):
        movement = receive_stock(stock, 10)
        movement.quantity = 999

        with pytest.raises(ValueError):
            movement.save()

    def test_movements_cannot_be_deleted(self, stock):
        movement = receive_stock(stock, 10)

        with pytest.raises(ValueError):
            movement.delete()

    def test_current_stock_is_reconstructable_from_the_ledger(self, stock):
        receive_stock(stock, 100)
        reserve_stock(stock, 20)
        ship_stock(stock, 20)
        restock_return(stock, 5)
        write_off(stock, 3, reason="Damaged")
        adjust_stock(stock, 80, reason="Stock count")

        stock.refresh_from_db()
        rebuilt = rebuild_stock_from_ledger(stock)

        assert rebuilt["on_hand"] == stock.on_hand
        assert rebuilt["reserved"] == stock.reserved

    def test_every_movement_snapshots_resulting_levels(self, stock):
        receive_stock(stock, 10)
        receive_stock(stock, 5)

        movements = StockMovement.objects.filter(stock_item=stock).order_by(
            "created_at", "id"
        )
        assert [m.on_hand_after for m in movements] == [10, 15]

    def test_cannot_ship_below_zero(self, stock):
        receive_stock(stock, 5)
        reserve_stock(stock, 5)
        ship_stock(stock, 5)

        with pytest.raises(StockError):
            ship_stock(stock, 1)


class TestLowStock:
    def test_is_low_uses_the_product_threshold(self, product, stock):
        receive_stock(stock, 5)
        stock.refresh_from_db()
        assert stock.is_low is True

        receive_stock(stock, 10)
        stock.refresh_from_db()
        assert stock.is_low is False

    def test_reserved_stock_counts_towards_low(self, product, stock):
        receive_stock(stock, 10)
        reserve_stock(stock, 6)
        stock.refresh_from_db()

        assert stock.available == 4
        assert stock.is_low is True
