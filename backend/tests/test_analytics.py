from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.services import (
    courier_performance,
    dashboard,
    district_performance,
    product_performance,
    profit_report,
    reconciliation_health,
    resolve_period,
    sales_series,
    staff_performance,
)
from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.expenses.models import Expense, ExpenseCategory
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.returns.models import ItemCondition, ReturnReason
from apps.returns.services import create_return, receive_return, resolve_return
from apps.shipments.models import CodStatus
from apps.shipments.services import book_shipment

pytestmark = pytest.mark.django_db

_n = {"i": 0}


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti",
        selling_price=Decimal("1000.00"), cost_price=Decimal("600.00"),
    )
    receive_stock(get_or_create_stock_item(product, None), 500)
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


def make_order(shop, *, quantity=1, discount="0.00", district="Dhaka",
               product=None, actor=None):
    return create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": product or shop["product"], "quantity": quantity}],
        shipping={"district": district, "address_line": "House 12"},
        discount_amount=Decimal(discount),
        actor=actor or shop["owner"],
    )


def ship(shop, order, *, cost="70.00"):
    _n["i"] += 1
    order = transition_status(order, OrderStatus.CONFIRMED)
    shipment = book_shipment(
        order, shop["courier"], actor=shop["owner"],
        manual_consignment_id=f"CN-{_n['i']:05d}",
    )
    shipment.actual_cost = Decimal(cost)
    shipment.save()
    return order, shipment


def deliver(shop, order, shipment):
    shipment.delivered_at = timezone.now()
    shipment.cod_status = CodStatus.COLLECTED
    shipment.save()
    order.refresh_from_db()
    return transition_status(order, OrderStatus.DELIVERED)


class TestProfitFormula:
    def test_hand_computed_month_matches_the_report(self, shop):
        for _ in range(3):
            order = make_order(shop, quantity=2, discount="50.00")
            order, shipment = ship(shop, order, cost="70.00")
            deliver(shop, order, shipment)

        Expense.objects.create(
            store=shop["store"], date=timezone.localdate(),
            category=ExpenseCategory.AD_SPEND, amount=Decimal("1500.00"),
        )

        report = profit_report(shop["store"])

        assert report["delivered_orders"] == 3
        assert report["gross_sales"] == Decimal("6000.00")
        assert report["discounts"] == Decimal("150.00")
        assert report["net_sales"] == Decimal("5850.00")
        assert report["delivery_revenue"] == Decimal("180.00")
        assert report["cogs"] == Decimal("3600.00")
        assert report["delivery_cost"] == Decimal("210.00")
        assert report["gross_profit"] == Decimal("2220.00")
        assert report["operating_expenses"] == Decimal("1500.00")
        assert report["net_profit"] == Decimal("720.00")

    def test_revenue_is_recognised_on_delivery_not_creation(self, shop):
        make_order(shop, quantity=2)

        report = profit_report(shop["store"])

        assert report["delivered_orders"] == 0
        assert report["gross_sales"] == Decimal("0.00")

    def test_shipped_but_undelivered_is_not_revenue(self, shop):
        order = make_order(shop, quantity=2)
        ship(shop, order)

        report = profit_report(shop["store"])

        assert report["gross_sales"] == Decimal("0.00")
        assert report["delivery_cost"] == Decimal("70.00")

    def test_return_loss_reduces_net_profit(self, shop):
        order = make_order(shop, quantity=2)
        order, shipment = ship(shop, order)
        order = deliver(shop, order, shipment)

        before = profit_report(shop["store"])["net_profit"]

        create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED,
            return_charge=Decimal("60.00"), actor=shop["owner"],
        )

        after = profit_report(shop["store"])
        assert after["net_profit"] < before
        assert after["return_loss"] >= Decimal("60.00")

    def test_written_off_stock_counts_as_loss(self, shop):
        order = make_order(shop, quantity=2)
        order, shipment = ship(shop, order)
        order = deliver(shop, order, shipment)

        record = create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED,
            actor=shop["owner"],
        )
        receive_return(record)
        resolve_return(
            record,
            item_dispositions=[{
                "return_item": record.items.first().id,
                "condition": ItemCondition.DAMAGED,
                "restock": False,
            }],
            actor=shop["owner"],
        )

        report = profit_report(shop["store"])
        assert report["return_breakdown"]["written_off_value"] == Decimal("1200.00")

    def test_empty_store_returns_zeros_not_errors(self, shop):
        report = profit_report(shop["store"])

        assert report["net_profit"] == Decimal("0.00")
        assert report["net_margin_percent"] == Decimal("0.00")

    def test_margin_percent_is_computed(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order, cost="0.00")
        deliver(shop, order, shipment)

        report = profit_report(shop["store"])

        assert report["net_sales"] == Decimal("1000.00")
        assert report["net_profit"] == Decimal("460.00")
        assert report["net_margin_percent"] == Decimal("46.00")

    def test_period_filter_excludes_older_orders(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        order = deliver(shop, order, shipment)

        from apps.orders.models import Order

        old = timezone.now() - timedelta(days=60)
        Order.objects.filter(pk=order.pk).update(delivered_at=old)

        report = profit_report(shop["store"])
        assert report["delivered_orders"] == 0

    def test_explicit_date_range_is_honoured(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        today = timezone.localdate()
        report = profit_report(
            shop["store"], date_from=today, date_to=today
        )
        assert report["delivered_orders"] == 1


class TestPeriodResolution:
    def test_defaults_to_last_thirty_days(self):
        start, end = resolve_period()
        assert (end - start).days == 29

    def test_accepts_iso_strings(self):
        start, end = resolve_period("2026-01-01", "2026-01-31")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)

    def test_reversed_range_is_corrected(self):
        start, end = resolve_period("2026-01-31", "2026-01-01")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)


class TestDashboard:
    def test_counts_today(self, shop):
        make_order(shop, quantity=1)
        make_order(shop, quantity=1)

        data = dashboard(shop["store"])

        assert data["today"]["orders"] == 2
        assert data["pending_confirmation"] == 2

    def test_delivered_today_shows_sales(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        data = dashboard(shop["store"])

        assert data["today"]["delivered"] == 1
        assert data["today"]["sales"] == Decimal("1000.00")

    def test_low_stock_is_surfaced(self, shop):
        thin = Product.objects.create(
            store=shop["store"], name="Rare Item",
            selling_price=Decimal("500"), low_stock_threshold=10,
        )
        receive_stock(get_or_create_stock_item(thin, None), 3)

        data = dashboard(shop["store"])
        names = {row["product_name"] for row in data["low_stock"]}

        assert "Rare Item" in names

    def test_cod_buckets_are_reported(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)

        data = dashboard(shop["store"])
        assert data["cod"]["in_transit"]["count"] == 1

    def test_top_products_ranked_by_revenue(self, shop):
        cheap = Product.objects.create(
            store=shop["store"], name="Cheap",
            selling_price=Decimal("100"), cost_price=Decimal("50"),
        )
        receive_stock(get_or_create_stock_item(cheap, None), 100)

        for product, quantity in ((shop["product"], 2), (cheap, 1)):
            order = make_order(shop, quantity=quantity, product=product)
            order, shipment = ship(shop, order)
            deliver(shop, order, shipment)

        data = dashboard(shop["store"])
        assert data["top_products"][0]["product_name"] == "Cotton Kurti"

    def test_change_against_yesterday_is_none_when_no_baseline(self, shop):
        make_order(shop, quantity=1)

        data = dashboard(shop["store"])
        assert data["change"]["orders"] is None

    def test_dashboard_is_scoped(self, shop, make_user, make_store):
        make_order(shop, quantity=1)
        stranger = make_store(make_user(email="bob@example.com"), name="Bob")

        data = dashboard(stranger)
        assert data["today"]["orders"] == 0


class TestSalesSeries:
    def test_groups_delivered_orders_by_day(self, shop):
        for _ in range(2):
            order = make_order(shop, quantity=1)
            order, shipment = ship(shop, order)
            deliver(shop, order, shipment)

        data = sales_series(shop["store"], group_by="day")

        assert len(data["series"]) == 1
        assert data["series"][0]["delivered_orders"] == 2

    def test_includes_days_with_orders_but_no_deliveries(self, shop):
        make_order(shop, quantity=1)

        data = sales_series(shop["store"])

        assert len(data["series"]) == 1
        assert data["series"][0]["placed_orders"] == 1
        assert data["series"][0]["delivered_orders"] == 0

    def test_monthly_grouping(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        data = sales_series(shop["store"], group_by="month")
        assert data["group_by"] == "month"
        assert len(data["series"]) == 1


class TestProductReport:
    def test_reports_units_revenue_and_margin(self, shop):
        order = make_order(shop, quantity=3)
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        data = product_performance(shop["store"])
        row = data["products"][0]

        assert row["units"] == 3
        assert row["revenue"] == Decimal("3000.00")
        assert row["cost"] == Decimal("1800.00")
        assert row["margin"] == Decimal("1200.00")
        assert row["margin_percent"] == Decimal("40.00")

    def test_return_rate_per_product(self, shop):
        first = make_order(shop, quantity=2)
        first, shipment = ship(shop, first)
        deliver(shop, first, shipment)

        second = make_order(shop, quantity=2)
        second, shipment2 = ship(shop, second)
        second = deliver(shop, second, shipment2)
        create_return(
            shop["store"], second, reason=ReturnReason.SIZE_ISSUE,
            actor=shop["owner"],
        )

        data = product_performance(shop["store"])
        row = data["products"][0]

        assert row["returned_units"] == 2
        assert row["return_rate"] > Decimal("0.00")

    def test_only_delivered_orders_count(self, shop):
        make_order(shop, quantity=5)

        data = product_performance(shop["store"])
        assert data["products"] == []


class TestCourierReport:
    def test_success_and_return_rates(self, shop):
        delivered_order = make_order(shop, quantity=1)
        delivered_order, s1 = ship(shop, delivered_order)
        deliver(shop, delivered_order, s1)

        returned_order = make_order(shop, quantity=1)
        returned_order, s2 = ship(shop, returned_order)
        returned_order = deliver(shop, returned_order, s2)
        create_return(
            shop["store"], returned_order, reason=ReturnReason.DAMAGED,
            actor=shop["owner"],
        )

        data = courier_performance(shop["store"])
        row = data["couriers"][0]

        assert row["shipped"] == 2
        assert row["delivered"] == 2
        assert row["returned"] == 1
        assert row["return_rate"] == Decimal("50.00")

    def test_average_cost_per_parcel(self, shop):
        for cost in ("60.00", "80.00"):
            order = make_order(shop, quantity=1)
            order, shipment = ship(shop, order, cost=cost)
            deliver(shop, order, shipment)

        data = courier_performance(shop["store"])
        assert data["couriers"][0]["average_cost"] == Decimal("70.00")


class TestDistrictReport:
    def test_groups_by_district(self, shop):
        for district in ("Dhaka", "Dhaka", "Sylhet"):
            make_order(shop, quantity=1, district=district)

        data = district_performance(shop["store"])
        rows = {r["shipping_district"]: r["total"] for r in data["districts"]}

        assert rows["Dhaka"] == 2
        assert rows["Sylhet"] == 1

    def test_success_rate_uses_shipped_orders(self, shop):
        order = make_order(shop, quantity=1, district="Khulna")
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        data = district_performance(shop["store"])
        row = next(
            r for r in data["districts"] if r["shipping_district"] == "Khulna"
        )
        assert row["success_rate"] == Decimal("100.00")


class TestStaffReport:
    def test_attributes_orders_to_creator(self, shop, make_user, make_member):
        from apps.stores.models import StoreRole

        staff = make_user(email="staff@example.com", full_name="Sadia")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        make_order(shop, quantity=1, actor=shop["owner"])
        make_order(shop, quantity=1, actor=staff)
        make_order(shop, quantity=1, actor=staff)

        data = staff_performance(shop["store"])
        rows = {r["created_by__full_name"]: r["created"] for r in data["staff"]}

        assert rows["Sadia"] == 2

    def test_confirmation_rate(self, shop):
        first = make_order(shop, quantity=1)
        transition_status(first, OrderStatus.CONFIRMED)
        make_order(shop, quantity=1)

        data = staff_performance(shop["store"])
        assert data["staff"][0]["confirmation_rate"] == Decimal("50.00")


class TestReconciliationHealth:
    def test_coverage_is_zero_without_settlements(self, shop):
        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        deliver(shop, order, shipment)

        data = reconciliation_health(shop["store"])

        assert data["delivered_cod_shipments"] == 1
        assert data["settled_shipments"] == 0
        assert data["coverage_percent"] == Decimal("0.00")

    def test_coverage_after_settlement(self, shop):
        from apps.payments.services import (
            commit_settlement,
            create_settlement_draft,
            parse_settlement_csv,
        )

        order = make_order(shop, quantity=1)
        order, shipment = ship(shop, order)
        order = deliver(shop, order, shipment)

        rows = parse_settlement_csv(
            f"consignment_id,amount,charge\n"
            f"{shipment.consignment_id},{order.cod_amount},70\n"
        )
        settlement = create_settlement_draft(
            shop["store"], shop["courier"], rows, actor=shop["owner"]
        )
        commit_settlement(settlement, actor=shop["owner"])

        data = reconciliation_health(shop["store"])
        assert data["coverage_percent"] == Decimal("100.00")
