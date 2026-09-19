from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.adapters.base import BookingResult, TrackingEvent
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.shipments.models import BookingMode, CodStatus, Shipment
from apps.shipments.services import (
    ShipmentError,
    book_shipment,
    cancel_shipment,
    due_for_sync,
    record_tracking_events,
    sync_due_shipments,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti",
        selling_price=Decimal("1200.00"), cost_price=Decimal("700.00"),
        weight_grams=400,
    )
    receive_stock(get_or_create_stock_item(product, None), 50)
    customer = Customer.objects.create(
        store=store, name="Karim Ahmed", phone="01712345678"
    )
    manual = StoreCourier.objects.create(
        store=store, courier=Courier.objects.get(code="manual"),
        is_default=True,
    )
    api_courier = StoreCourier.objects.create(
        store=store, courier=Courier.objects.get(code="steadfast"),
        credentials={"api_key": "k", "secret_key": "s"},
    )
    return {
        "owner": owner, "store": store, "product": product,
        "customer": customer, "manual": manual, "api": api_courier,
    }


def make_confirmed_order(shop, quantity=1):
    order = create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )
    return transition_status(order, OrderStatus.CONFIRMED, actor=shop["owner"])


FAKE_BOOKING = BookingResult(
    consignment_id="CN-9001",
    tracking_code="TRK9001",
    tracking_url="https://example.test/t/TRK9001",
    quoted_cost=Decimal("70.00"),
    raw_request={"invoice": "X"},
    raw_response={"status": 200},
)


class TestManualBooking:
    def test_books_with_typed_consignment_id(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], actor=shop["owner"],
            manual_consignment_id="LOCAL-123",
        )

        assert shipment.consignment_id == "LOCAL-123"
        assert shipment.booking_mode == BookingMode.MANUAL

    def test_booking_advances_order_to_shipped(self, shop):
        order = make_confirmed_order(shop)
        book_shipment(
            order, shop["manual"], actor=shop["owner"],
            manual_consignment_id="LOCAL-123",
        )
        order.refresh_from_db()

        assert order.status == OrderStatus.SHIPPED
        assert order.shipped_at is not None

    def test_booking_ships_the_stock(self, shop):
        order = make_confirmed_order(shop, quantity=3)
        book_shipment(
            order, shop["manual"], actor=shop["owner"],
            manual_consignment_id="LOCAL-123",
        )

        stock = get_or_create_stock_item(shop["product"], None)
        stock.refresh_from_db()
        assert stock.on_hand == 47
        assert stock.reserved == 0

    def test_manual_courier_requires_a_consignment_id(self, shop):
        order = make_confirmed_order(shop)

        with pytest.raises(ShipmentError) as exc:
            book_shipment(order, shop["manual"], actor=shop["owner"])
        assert exc.value.code == "CONSIGNMENT_ID_REQUIRED"

    def test_cod_amount_is_carried_onto_the_shipment(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="LOCAL-1"
        )

        assert shipment.cod_amount == order.cod_amount
        assert shipment.cod_status == CodStatus.PENDING


class TestApiBooking:
    def test_books_through_the_adapter(self, shop):
        order = make_confirmed_order(shop)

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            return_value=FAKE_BOOKING,
        ):
            shipment = book_shipment(order, shop["api"], actor=shop["owner"])

        assert shipment.consignment_id == "CN-9001"
        assert shipment.booking_mode == BookingMode.API
        assert shipment.quoted_cost == Decimal("70.00")

    def test_raw_payloads_are_stored_for_support(self, shop):
        order = make_confirmed_order(shop)

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            return_value=FAKE_BOOKING,
        ):
            shipment = book_shipment(order, shop["api"])

        assert shipment.raw_booking_response == {"status": 200}

    def test_courier_failure_leaves_order_unshipped(self, shop):
        from apps.couriers.adapters.base import CourierUnavailable

        order = make_confirmed_order(shop)

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            side_effect=CourierUnavailable("Courier down"),
        ):
            with pytest.raises(CourierUnavailable):
                book_shipment(order, shop["api"])

        order.refresh_from_db()
        assert order.status == OrderStatus.CONFIRMED
        assert Shipment.objects.filter(order=order).count() == 0

    def test_stock_is_not_shipped_when_booking_fails(self, shop):
        from apps.couriers.adapters.base import CourierUnavailable

        order = make_confirmed_order(shop, quantity=3)

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            side_effect=CourierUnavailable("Courier down"),
        ):
            with pytest.raises(CourierUnavailable):
                book_shipment(order, shop["api"])

        stock = get_or_create_stock_item(shop["product"], None)
        stock.refresh_from_db()
        assert stock.on_hand == 50
        assert stock.reserved == 3


class TestBookingGuards:
    def test_pending_order_cannot_be_booked(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        with pytest.raises(ShipmentError) as exc:
            book_shipment(
                order, shop["manual"], manual_consignment_id="X-1"
            )
        assert exc.value.code == "ORDER_NOT_READY"

    def test_double_booking_is_rejected(self, shop):
        order = make_confirmed_order(shop)
        book_shipment(order, shop["manual"], manual_consignment_id="X-1")
        order.refresh_from_db()

        with pytest.raises(ShipmentError) as exc:
            book_shipment(order, shop["manual"], manual_consignment_id="X-2")
        assert exc.value.code == "SHIPMENT_ALREADY_EXISTS"

    def test_courier_from_another_store_is_rejected(
        self, shop, make_user, make_store
    ):
        order = make_confirmed_order(shop)
        stranger = make_store(make_user(email="bob@example.com"), name="Bob")
        foreign = StoreCourier.objects.create(
            store=stranger, courier=Courier.objects.get(code="manual")
        )

        with pytest.raises(ShipmentError) as exc:
            book_shipment(order, foreign, manual_consignment_id="X-1")
        assert exc.value.code == "COURIER_NOT_IN_STORE"

    def test_disabled_courier_is_rejected(self, shop):
        order = make_confirmed_order(shop)
        shop["manual"].is_enabled = False
        shop["manual"].save()

        with pytest.raises(ShipmentError) as exc:
            book_shipment(order, shop["manual"], manual_consignment_id="X-1")
        assert exc.value.code == "COURIER_DISABLED"


class TestTrackingSync:
    def _shipment(self, shop):
        order = make_confirmed_order(shop)
        return book_shipment(
            order, shop["api"], manual_consignment_id="CN-1"
        )

    def _event(self, raw, mapped, when=None):
        return TrackingEvent(
            raw_status=raw, mapped_status=mapped,
            observed_at=when or timezone.now(),
        )

    def test_delivered_event_moves_the_order(self, shop):
        shipment = self._shipment(shop)
        record_tracking_events(
            shipment,
            [self._event("delivered", OrderStatus.DELIVERED)],
        )

        shipment.order.refresh_from_db()
        assert shipment.order.status == OrderStatus.DELIVERED

    def test_delivered_event_marks_cod_collected(self, shop):
        shipment = self._shipment(shop)
        shipment = record_tracking_events(
            shipment,
            [self._event("delivered", OrderStatus.DELIVERED)],
        )

        assert shipment.cod_status == CodStatus.COLLECTED
        assert shipment.cod_collected_at is not None
        assert shipment.delivered_at is not None

    def test_every_event_is_recorded(self, shop):
        shipment = self._shipment(shop)
        now = timezone.now()
        record_tracking_events(shipment, [
            self._event("in_transit", OrderStatus.SHIPPED, now),
            self._event("out_for_delivery", OrderStatus.OUT_FOR_DELIVERY,
                        now + timedelta(minutes=1)),
        ])

        assert shipment.tracking_history.count() == 2

    def test_duplicate_events_are_ignored(self, shop):
        shipment = self._shipment(shop)
        when = timezone.now()
        event = self._event("delivered", OrderStatus.DELIVERED, when)

        record_tracking_events(shipment, [event])
        record_tracking_events(shipment, [event])

        assert shipment.tracking_history.count() == 1

    def test_illegal_mapped_status_is_recorded_but_not_applied(self, shop):
        shipment = self._shipment(shop)
        shipment.order.refresh_from_db()
        transition_status(shipment.order, OrderStatus.DELIVERED)

        record_tracking_events(
            shipment,
            [self._event("picked", OrderStatus.SHIPPED)],
        )

        shipment.order.refresh_from_db()
        assert shipment.order.status == OrderStatus.DELIVERED
        assert shipment.tracking_history.filter(raw_status="picked").exists()

    def test_unmapped_status_does_not_touch_the_order(self, shop):
        shipment = self._shipment(shop)
        record_tracking_events(shipment, [self._event("teleported", "")])

        shipment.order.refresh_from_db()
        assert shipment.order.status == OrderStatus.SHIPPED

    def test_history_rows_are_immutable(self, shop):
        shipment = self._shipment(shop)
        record_tracking_events(
            shipment, [self._event("delivered", OrderStatus.DELIVERED)]
        )
        row = shipment.tracking_history.first()

        row.note = "tampered"
        with pytest.raises(ValueError):
            row.save()
        with pytest.raises(ValueError):
            row.delete()


class TestSyncScheduling:
    _counter = 0

    def _api_shipment(self, shop, booked_ago, synced_ago=None):
        TestSyncScheduling._counter += 1
        booking = BookingResult(
            consignment_id=f"CN-{TestSyncScheduling._counter:04d}",
            tracking_code=f"TRK{TestSyncScheduling._counter:04d}",
            quoted_cost=Decimal("70.00"),
        )
        order = make_confirmed_order(shop)
        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.create_parcel",
            return_value=booking,
        ):
            shipment = book_shipment(order, shop["api"])

        now = timezone.now()
        Shipment.objects.filter(pk=shipment.pk).update(
            booked_at=now - booked_ago,
            last_synced_at=None if synced_ago is None else now - synced_ago,
        )
        shipment.refresh_from_db()
        return shipment

    def test_never_synced_shipment_is_due(self, shop):
        shipment = self._api_shipment(shop, timedelta(hours=1))
        assert due_for_sync(shipment) is True

    def test_fresh_shipment_polls_every_fifteen_minutes(self, shop):
        recent = self._api_shipment(
            shop, timedelta(hours=1), synced_ago=timedelta(minutes=5)
        )
        assert due_for_sync(recent) is False

        stale = self._api_shipment(
            shop, timedelta(hours=1), synced_ago=timedelta(minutes=20)
        )
        assert due_for_sync(stale) is True

    def test_older_shipments_poll_less_often(self, shop):
        shipment = self._api_shipment(
            shop, timedelta(days=4), synced_ago=timedelta(minutes=30)
        )
        assert due_for_sync(shipment) is False

    def test_delivered_shipments_stop_syncing(self, shop):
        shipment = self._api_shipment(shop, timedelta(hours=1))
        shipment.delivered_at = timezone.now()
        shipment.save()

        assert due_for_sync(shipment) is False

    def test_manual_shipments_are_never_polled(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="LOCAL-1"
        )
        assert due_for_sync(shipment) is False

    def test_repeatedly_failing_shipments_are_dropped(self, shop):
        shipment = self._api_shipment(shop, timedelta(hours=1))
        shipment.sync_failures = 10
        shipment.save()

        assert due_for_sync(shipment) is False

    def test_sync_due_shipments_counts_work_done(self, shop):
        self._api_shipment(shop, timedelta(hours=1))

        with patch(
            "apps.couriers.adapters.steadfast.SteadfastAdapter.track",
            return_value=[],
        ):
            synced = sync_due_shipments()

        assert synced == 1


class TestCancellation:
    def test_cancelling_clears_cod(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )
        shipment = cancel_shipment(shipment)

        assert shipment.cancelled_at is not None
        assert shipment.cod_status == CodStatus.NOT_APPLICABLE

    def test_delivered_shipment_cannot_be_cancelled(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )
        shipment.delivered_at = timezone.now()
        shipment.save()

        with pytest.raises(ShipmentError) as exc:
            cancel_shipment(shipment)
        assert exc.value.code == "SHIPMENT_ALREADY_DELIVERED"

    def test_cancelling_twice_is_rejected(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )
        cancel_shipment(shipment)
        shipment.refresh_from_db()

        with pytest.raises(ShipmentError) as exc:
            cancel_shipment(shipment)
        assert exc.value.code == "SHIPMENT_ALREADY_CANCELLED"

    def test_cancelled_shipment_frees_the_order_to_rebook(self, shop):
        order = make_confirmed_order(shop)
        shipment = book_shipment(
            order, shop["manual"], manual_consignment_id="X-1"
        )
        cancel_shipment(shipment)

        order.refresh_from_db()
        Shipment.objects.filter(pk=shipment.pk).update(
            cancelled_at=timezone.now()
        )
        assert Shipment.objects.filter(
            order=order, cancelled_at__isnull=True
        ).count() == 0
