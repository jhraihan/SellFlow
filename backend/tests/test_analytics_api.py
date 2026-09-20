from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.shipments.models import CodStatus
from apps.shipments.services import book_shipment
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

BASE = "/api/v1/analytics/"
_n = {"i": 0}


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti",
        selling_price=Decimal("1000.00"), cost_price=Decimal("600.00"),
    )
    receive_stock(get_or_create_stock_item(product, None), 200)
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


def delivered(shop, quantity=1):
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
        manual_consignment_id=f"CN-{_n['i']:05d}",
    )
    shipment.actual_cost = Decimal("70.00")
    shipment.delivered_at = timezone.now()
    shipment.cod_status = CodStatus.COLLECTED
    shipment.save()
    order.refresh_from_db()
    return transition_status(order, OrderStatus.DELIVERED)


class TestDashboardEndpoint:
    def test_returns_kpis(self, shop, auth):
        delivered(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}dashboard/"
        )

        assert response.status_code == 200
        assert response.data["today"]["delivered"] == 1
        assert Decimal(response.data["today"]["sales"]) == Decimal("1000.00")
        assert "cod" in response.data
        assert "low_stock" in response.data

    def test_requires_analytics_capability(
        self, shop, auth, make_user, make_member
    ):
        staff = make_user(email="staff@example.com")
        make_member(shop["store"], staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=shop["store"]).get(f"{BASE}dashboard/")
        assert response.status_code == 403

    def test_accountant_can_view(self, shop, auth, make_user, make_member):
        accountant = make_user(email="acc@example.com")
        make_member(shop["store"], accountant, StoreRole.ACCOUNTANT)

        response = auth(accountant, store=shop["store"]).get(
            f"{BASE}dashboard/"
        )
        assert response.status_code == 200

    def test_scoped_to_the_store(self, shop, auth, make_user, make_store):
        delivered(shop)
        stranger = make_user(email="bob@example.com")
        other = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other).get(f"{BASE}dashboard/")
        assert response.data["today"]["delivered"] == 0


class TestProfitEndpoint:
    def test_returns_the_full_breakdown(self, shop, auth):
        delivered(shop, quantity=2)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}profit/"
        )

        assert response.status_code == 200
        for key in (
            "gross_sales", "net_sales", "cogs", "delivery_cost",
            "gross_profit", "return_loss", "operating_expenses",
            "net_profit", "net_margin_percent",
        ):
            assert key in response.data

    def test_date_range_is_applied(self, shop, auth):
        delivered(shop)
        today = timezone.localdate()

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}profit/?date_from={today}&date_to={today}"
        )
        assert response.data["delivered_orders"] == 1


class TestSalesEndpoint:
    def test_returns_summary_and_series(self, shop, auth):
        delivered(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}sales/"
        )

        assert response.status_code == 200
        assert "summary" in response.data
        assert len(response.data["series"]) == 1

    def test_group_by_month(self, shop, auth):
        delivered(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}sales/?group_by=month"
        )
        assert response.data["group_by"] == "month"

    def test_invalid_group_by_falls_back_to_day(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}sales/?group_by=nonsense"
        )
        assert response.data["group_by"] == "day"


class TestReportEndpoints:
    @pytest.mark.parametrize(
        "path,key",
        [
            ("products/", "products"),
            ("couriers/", "couriers"),
            ("districts/", "districts"),
            ("staff/", "staff"),
        ],
    )
    def test_reports_respond(self, shop, auth, path, key):
        delivered(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}{path}"
        )

        assert response.status_code == 200
        assert key in response.data

    def test_reconciliation_health(self, shop, auth):
        delivered(shop)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}reconciliation/"
        )

        assert response.status_code == 200
        assert response.data["delivered_cod_shipments"] == 1
        assert response.data["coverage_percent"] == "0.00"


class TestExport:
    def test_exports_products_csv(self, shop, auth):
        delivered(shop, quantity=2)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}export/?report=products"
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        body = response.content.decode()
        assert "Cotton Kurti" in body

    def test_unknown_report_is_rejected(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}export/?report=nope"
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "UNKNOWN_REPORT"

    def test_empty_report_returns_empty_csv(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}export/?report=products"
        )

        assert response.status_code == 200
        assert response.content.decode().strip() == ""


class TestMoneyIsNeverAFloat:
    def _walk(self, value, path=""):
        floats = []
        if isinstance(value, float):
            floats.append(path)
        elif isinstance(value, dict):
            for key, item in value.items():
                floats += self._walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                floats += self._walk(item, f"{path}[{index}]")
        return floats

    @pytest.mark.parametrize(
        "path",
        ["dashboard/", "profit/", "sales/", "products/", "couriers/",
         "districts/", "staff/", "reconciliation/"],
    )
    def test_no_endpoint_renders_money_as_float(self, shop, auth, path):
        import json

        delivered(shop, quantity=2)

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BASE}{path}"
        )
        payload = json.loads(response.content.decode())

        assert self._walk(payload) == [], (
            f"{path} rendered money as a float, which loses precision."
        )
