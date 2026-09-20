from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.orders.models import OrderStatus, PaymentStatus
from apps.orders.services import create_order, transition_status
from apps.payments.models import (
    MatchStatus,
    Payment,
    PaymentDirection,
    PaymentMethod,
    SettlementStatus,
)
from apps.payments.services import (
    SettlementError,
    cod_ledger,
    commit_settlement,
    create_settlement_draft,
    parse_settlement_csv,
    record_payment,
)
from apps.shipments.models import CodStatus, Shipment
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


def shipped_order(shop, quantity=1, consignment="CN-1"):
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
        manual_consignment_id=consignment,
    )
    return order, shipment


def deliver(shipment):
    shipment.delivered_at = timezone.now()
    shipment.cod_status = CodStatus.COLLECTED
    shipment.cod_collected_at = timezone.now()
    shipment.save()
    order = shipment.order
    order.refresh_from_db()
    transition_status(order, OrderStatus.DELIVERED)
    return shipment


class TestPaymentRecording:
    def test_advance_reduces_cod(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        record_payment(
            shop["store"], amount=Decimal("500.00"),
            method=PaymentMethod.BKASH, order=order,
        )
        order.refresh_from_db()

        assert order.advance_paid == Decimal("500.00")
        assert order.cod_amount == Decimal("760.00")
        assert order.payment_status == PaymentStatus.PARTIALLY_PAID

    def test_full_payment_marks_order_paid(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        record_payment(
            shop["store"], amount=order.total_amount,
            method=PaymentMethod.BKASH, order=order,
        )
        order.refresh_from_db()

        assert order.cod_amount == Decimal("0.00")
        assert order.payment_status == PaymentStatus.PAID

    def test_several_payments_accumulate(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        record_payment(shop["store"], amount=Decimal("300.00"),
                       method=PaymentMethod.BKASH, order=order)
        record_payment(shop["store"], amount=Decimal("200.00"),
                       method=PaymentMethod.NAGAD, order=order)
        order.refresh_from_db()

        assert order.advance_paid == Decimal("500.00")

    def test_refund_reduces_the_net(self, shop):
        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": shop["product"], "quantity": 1}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
        )

        record_payment(shop["store"], amount=Decimal("500.00"),
                       method=PaymentMethod.BKASH, order=order)
        record_payment(
            shop["store"], amount=Decimal("500.00"),
            method=PaymentMethod.BKASH, order=order,
            direction=PaymentDirection.OUT,
        )
        order.refresh_from_db()

        assert order.advance_paid == Decimal("0.00")
        assert order.payment_status == PaymentStatus.REFUNDED

    def test_zero_amount_rejected(self, shop):
        from apps.payments.services import PaymentError

        with pytest.raises(PaymentError):
            record_payment(
                shop["store"], amount=Decimal("0"),
                method=PaymentMethod.CASH,
            )

    def test_payment_without_an_order_is_allowed(self, shop):
        payment = record_payment(
            shop["store"], amount=Decimal("1000.00"),
            method=PaymentMethod.CASH, note="Counter sale",
        )
        assert payment.order is None


class TestSettlementParsing:
    def test_reads_standard_columns(self):
        csv_text = (
            "consignment_id,collected_amount,delivery_charge\n"
            "CN-1,1260.00,70.00\n"
        )
        rows = parse_settlement_csv(csv_text)

        assert len(rows) == 1
        assert rows[0]["consignment_id"] == "CN-1"
        assert rows[0]["collected_amount"] == Decimal("1260.00")
        assert rows[0]["net_amount"] == Decimal("1190.00")

    def test_tolerates_alternate_column_names(self):
        csv_text = "Tracking Code,COD Amount,Courier Charge\nCN-2,500,50\n"
        rows = parse_settlement_csv(csv_text)

        assert rows[0]["consignment_id"] == "CN-2"
        assert rows[0]["collected_amount"] == Decimal("500.00")

    def test_strips_currency_and_separators(self):
        csv_text = "consignment_id,amount,charge\nCN-3,\"1,260.00\",Tk 70\n"
        rows = parse_settlement_csv(csv_text)

        assert rows[0]["collected_amount"] == Decimal("1260.00")
        assert rows[0]["deducted_charge"] == Decimal("70.00")

    def test_unparseable_amount_becomes_zero(self):
        csv_text = "consignment_id,amount\nCN-4,not-a-number\n"
        rows = parse_settlement_csv(csv_text)

        assert rows[0]["collected_amount"] == Decimal("0.00")


class TestSettlementMatching:
    def _draft(self, shop, rows):
        return create_settlement_draft(
            shop["store"], shop["courier"], rows,
            statement_reference="STMT-1", actor=shop["owner"],
        )

    def test_matching_row_is_matched(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-100")
        deliver(shipment)

        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\nCN-100,{order.cod_amount},70\n"
        )
        settlement = self._draft(shop, rows)

        assert settlement.matched_count == 1
        assert settlement.lines.first().match_status == MatchStatus.MATCHED

    def test_unknown_consignment_is_unmatched(self, shop):
        rows = parse_settlement_csv(
            "consignment_id,amount,charge\nGHOST-1,500,50\n"
        )
        settlement = self._draft(shop, rows)

        assert settlement.unmatched_count == 1
        assert settlement.lines.first().match_status == MatchStatus.UNMATCHED

    def test_wrong_amount_is_flagged_as_mismatch(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-101")
        deliver(shipment)

        rows = parse_settlement_csv(
            "consignment_id,amount,charge\nCN-101,999.00,70\n"
        )
        settlement = self._draft(shop, rows)

        assert settlement.mismatch_count == 1
        line = settlement.lines.first()
        assert line.match_status == MatchStatus.AMOUNT_MISMATCH
        assert line.expected_amount == order.cod_amount

    def test_already_settled_shipment_is_flagged(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-102")
        deliver(shipment)
        shipment.cod_status = CodStatus.SETTLED
        shipment.save()

        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\nCN-102,{order.cod_amount},70\n"
        )
        settlement = self._draft(shop, rows)

        assert settlement.lines.first().match_status == MatchStatus.ALREADY_SETTLED

    def test_draft_changes_nothing_until_committed(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-103")
        deliver(shipment)

        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\nCN-103,{order.cod_amount},70\n"
        )
        self._draft(shop, rows)

        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.COLLECTED
        assert Payment.objects.filter(order=order).count() == 0

    def test_shipment_from_another_courier_does_not_match(
        self, shop, make_user, make_store
    ):
        order, shipment = shipped_order(shop, consignment="CN-104")
        deliver(shipment)

        other = StoreCourier.objects.create(
            store=shop["store"],
            courier=Courier.objects.get(code="steadfast"),
            credentials={"api_key": "k", "secret_key": "s"},
        )
        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\nCN-104,{order.cod_amount},70\n"
        )
        settlement = create_settlement_draft(
            shop["store"], other, rows, actor=shop["owner"]
        )

        assert settlement.unmatched_count == 1


class TestSettlementCommit:
    def _draft_for(self, shop, consignment, amount=None, charge="70"):
        order, shipment = shipped_order(shop, consignment=consignment)
        deliver(shipment)
        amount = amount if amount is not None else order.cod_amount
        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\n{consignment},{amount},{charge}\n"
        )
        settlement = create_settlement_draft(
            shop["store"], shop["courier"], rows,
            statement_reference="STMT-9", actor=shop["owner"],
        )
        return order, shipment, settlement

    def test_commit_marks_shipment_settled(self, shop):
        order, shipment, settlement = self._draft_for(shop, "CN-200")
        commit_settlement(settlement, actor=shop["owner"])

        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.SETTLED
        assert shipment.cod_settled_at is not None
        assert shipment.settlement_reference == "STMT-9"

    def test_commit_records_the_courier_charge(self, shop):
        order, shipment, settlement = self._draft_for(
            shop, "CN-201", charge="85"
        )
        commit_settlement(settlement, actor=shop["owner"])

        shipment.refresh_from_db()
        assert shipment.actual_cost == Decimal("85.00")

    def test_commit_creates_a_cod_payment(self, shop):
        order, shipment, settlement = self._draft_for(shop, "CN-202")
        commit_settlement(settlement, actor=shop["owner"])

        payment = Payment.objects.get(order=order, method=PaymentMethod.COD)
        assert payment.amount == order.cod_amount
        assert payment.reference == "CN-202"

    def test_commit_marks_the_order_paid(self, shop):
        order, shipment, settlement = self._draft_for(shop, "CN-203")
        commit_settlement(settlement, actor=shop["owner"])

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID

    def test_mismatched_lines_are_skipped_by_default(self, shop):
        order, shipment, settlement = self._draft_for(
            shop, "CN-204", amount="999.00"
        )

        with pytest.raises(SettlementError) as exc:
            commit_settlement(settlement, actor=shop["owner"])

        assert exc.value.code == "NOTHING_TO_SETTLE"
        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.COLLECTED

    def test_mismatches_can_be_committed_deliberately(self, shop):
        order, shipment, settlement = self._draft_for(
            shop, "CN-205", amount="999.00"
        )
        result = commit_settlement(
            settlement, actor=shop["owner"], include_mismatches=True
        )

        assert result["settled_count"] == 1
        shipment.refresh_from_db()
        assert shipment.cod_status == CodStatus.SETTLED

    def test_double_commit_is_rejected(self, shop):
        order, shipment, settlement = self._draft_for(shop, "CN-206")
        commit_settlement(settlement, actor=shop["owner"])
        settlement.refresh_from_db()

        with pytest.raises(SettlementError) as exc:
            commit_settlement(settlement, actor=shop["owner"])
        assert exc.value.code == "SETTLEMENT_ALREADY_COMMITTED"

    def test_commit_sets_status_and_timestamp(self, shop):
        order, shipment, settlement = self._draft_for(shop, "CN-207")
        result = commit_settlement(settlement, actor=shop["owner"])

        assert result["settlement"].status == SettlementStatus.COMMITTED
        assert result["settlement"].committed_at is not None


class TestCodLedger:
    def test_in_transit_counts_undelivered_cod(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-300")

        ledger = cod_ledger(shop["store"])
        assert ledger["in_transit"]["count"] == 1
        assert ledger["in_transit"]["amount"] == order.cod_amount

    def test_collected_but_unsettled_is_tracked(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-301")
        deliver(shipment)

        ledger = cod_ledger(shop["store"])
        assert ledger["collected_unsettled"]["count"] == 1
        assert ledger["in_transit"]["count"] == 0

    def test_settled_moves_out_of_outstanding(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-302")
        deliver(shipment)
        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\nCN-302,{order.cod_amount},70\n"
        )
        settlement = create_settlement_draft(
            shop["store"], shop["courier"], rows, actor=shop["owner"]
        )
        commit_settlement(settlement, actor=shop["owner"])

        ledger = cod_ledger(shop["store"])
        assert ledger["collected_unsettled"]["count"] == 0
        assert ledger["settled"]["count"] == 1

    def test_overdue_uses_the_store_threshold(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-303")
        deliver(shipment)

        Shipment.objects.filter(pk=shipment.pk).update(
            delivered_at=timezone.now() - timedelta(days=10)
        )

        ledger = cod_ledger(shop["store"])
        assert ledger["overdue"]["count"] == 1
        assert ledger["overdue_days"] == 7

    def test_recent_delivery_is_not_overdue(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-304")
        deliver(shipment)

        ledger = cod_ledger(shop["store"])
        assert ledger["overdue"]["count"] == 0

    def test_shortfall_is_surfaced(self, shop):
        order, shipment = shipped_order(shop, consignment="CN-305")
        deliver(shipment)

        rows = parse_settlement_csv(
            "consignment_id,amount,charge\nCN-305,1000.00,70\n"
        )
        settlement = create_settlement_draft(
            shop["store"], shop["courier"], rows, actor=shop["owner"]
        )
        commit_settlement(
            settlement, actor=shop["owner"], include_mismatches=True
        )

        ledger = cod_ledger(shop["store"])
        assert len(ledger["shortfalls"]) == 1
        shortfall = ledger["shortfalls"][0]
        assert shortfall["expected"] == order.cod_amount
        assert shortfall["received"] == Decimal("1000.00")
        assert ledger["shortfall_total"] > 0

    def test_ledger_is_scoped_to_the_store(
        self, shop, make_user, make_store
    ):
        shipped_order(shop, consignment="CN-306")

        stranger = make_store(make_user(email="bob@example.com"), name="Bob")
        ledger = cod_ledger(stranger)

        assert ledger["in_transit"]["count"] == 0
