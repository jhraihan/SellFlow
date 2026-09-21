from decimal import Decimal

import pytest

from apps.billing.models import Plan, Subscription
from apps.billing.services import (
    PlanLimitReached,
    activate_plan,
    check_order_allowance,
    get_or_create_subscription,
    usage_summary,
)
from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import (
    notify,
    scan_low_stock,
    scan_overdue_cod,
)
from apps.orders.models import OrderSource, OrderStatus
from apps.orders.services import create_order, transition_status
from apps.returns.models import ReturnReason
from apps.returns.services import create_return
from apps.shipments.models import CodStatus
from apps.shipments.services import book_shipment
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

NOTIFICATIONS = "/api/v1/notifications/"
BILLING = "/api/v1/billing/"
_n = {"i": 0}


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com")
    store = make_store(owner)
    product = Product.objects.create(
        store=store, name="Cotton Kurti",
        selling_price=Decimal("1000.00"), cost_price=Decimal("600.00"),
        low_stock_threshold=5,
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


def make_order(shop, quantity=1):
    return create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={"district": "Dhaka", "address_line": "House 12"},
        actor=shop["owner"],
    )


class TestNotifications:
    def test_notify_creates_a_row(self, shop):
        notification = notify(
            shop["store"], NotificationType.LOW_STOCK, "Running low"
        )

        assert notification.pk is not None
        assert notification.is_read is False

    def test_dedupe_key_prevents_repeats(self, shop):
        for _ in range(3):
            notify(
                shop["store"], NotificationType.LOW_STOCK, "Running low",
                dedupe_key="low-stock:1",
            )

        assert Notification.objects.for_store(shop["store"]).count() == 1

    def test_different_keys_create_separate_rows(self, shop):
        notify(shop["store"], NotificationType.LOW_STOCK, "A", dedupe_key="a")
        notify(shop["store"], NotificationType.LOW_STOCK, "B", dedupe_key="b")

        assert Notification.objects.for_store(shop["store"]).count() == 2

    def test_low_stock_scan_raises_alerts(self, shop):
        thin = Product.objects.create(
            store=shop["store"], name="Rare Item",
            selling_price=Decimal("500"), low_stock_threshold=10,
        )
        receive_stock(get_or_create_stock_item(thin, None), 3)

        created = scan_low_stock(shop["store"])
        titles = [n.title for n in created]

        assert any("Rare Item" in title for title in titles)

    def test_low_stock_scan_is_idempotent(self, shop):
        thin = Product.objects.create(
            store=shop["store"], name="Rare Item",
            selling_price=Decimal("500"), low_stock_threshold=10,
        )
        receive_stock(get_or_create_stock_item(thin, None), 3)

        scan_low_stock(shop["store"])
        scan_low_stock(shop["store"])

        count = Notification.objects.for_store(shop["store"]).filter(
            notification_type=NotificationType.LOW_STOCK
        ).count()
        assert count == 1

    def test_overdue_cod_scan(self, shop):
        from datetime import timedelta

        from django.utils import timezone

        from apps.shipments.models import Shipment

        order = make_order(shop)
        order = transition_status(order, OrderStatus.CONFIRMED)
        shipment = book_shipment(
            order, shop["courier"], manual_consignment_id="CN-OVERDUE"
        )
        Shipment.objects.filter(pk=shipment.pk).update(
            delivered_at=timezone.now() - timedelta(days=30),
            cod_status=CodStatus.COLLECTED,
        )

        alert = scan_overdue_cod(shop["store"])

        assert alert is not None
        assert alert.notification_type == NotificationType.COD_OVERDUE

    def test_no_overdue_means_no_alert(self, shop):
        assert scan_overdue_cod(shop["store"]) is None

    def test_return_raises_a_notification(self, shop):
        order = make_order(shop)
        order = transition_status(order, OrderStatus.CONFIRMED)
        book_shipment(order, shop["courier"], manual_consignment_id="CN-R1")
        order.refresh_from_db()
        order = transition_status(order, OrderStatus.DELIVERED)

        create_return(
            shop["store"], order, reason=ReturnReason.DAMAGED,
            actor=shop["owner"],
        )

        assert Notification.objects.for_store(shop["store"]).filter(
            notification_type=NotificationType.RETURN_RECORDED
        ).exists()

    def test_list_endpoint(self, shop, auth):
        notify(shop["store"], NotificationType.LOW_STOCK, "Running low")

        response = auth(shop["owner"], store=shop["store"]).get(NOTIFICATIONS)

        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_unread_count(self, shop, auth):
        notify(shop["store"], NotificationType.LOW_STOCK, "A", dedupe_key="a")
        notify(shop["store"], NotificationType.LOW_STOCK, "B", dedupe_key="b")

        response = auth(shop["owner"], store=shop["store"]).get(
            f"{NOTIFICATIONS}unread-count/"
        )
        assert response.data["unread"] == 2

    def test_mark_all_read(self, shop, auth):
        notify(shop["store"], NotificationType.LOW_STOCK, "A", dedupe_key="a")
        notify(shop["store"], NotificationType.LOW_STOCK, "B", dedupe_key="b")

        client = auth(shop["owner"], store=shop["store"])
        response = client.post(
            f"{NOTIFICATIONS}mark-read/", {"all": True}, format="json"
        )

        assert response.data["marked_read"] == 2
        assert client.get(f"{NOTIFICATIONS}unread-count/").data["unread"] == 0

    def test_notifications_are_scoped(
        self, shop, auth, make_user, make_store
    ):
        notify(shop["store"], NotificationType.LOW_STOCK, "Private")
        stranger = make_user(email="bob@example.com")
        other = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other).get(NOTIFICATIONS)
        assert response.data["results"] == []

    def test_scan_command_runs(self, shop):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("scan_alerts", stdout=out)
        assert "Scanned" in out.getvalue()


class TestPublicOrderForm:
    def test_store_page_lists_products(self, api, shop):
        response = api.get(f"/api/v1/public/stores/{shop['store'].slug}/")

        assert response.status_code == 200
        assert response.data["store"]["name"] == shop["store"].name
        assert len(response.data["products"]) == 1

    def test_unknown_store_is_404(self, api, shop):
        response = api.get("/api/v1/public/stores/nope/")
        assert response.status_code == 404

    def test_public_order_is_created(self, api, shop):
        response = api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "Nasrin Akter",
                "phone": "01911223344",
                "district": "Dhaka",
                "address_line": "House 9, Road 2",
                "items": [{"product": shop["product"].id, "quantity": 2}],
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["order_number"].startswith("ORD-")

        from apps.orders.models import Order

        order = Order.objects.get(order_number=response.data["order_number"])
        assert order.source == OrderSource.PUBLIC_FORM
        assert order.status == OrderStatus.PENDING

    def test_public_order_needs_no_auth(self, api, shop):
        api.credentials()
        response = api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "Nasrin", "phone": "01911223344",
                "district": "Dhaka", "address_line": "House 9",
                "items": [{"product": shop["product"].id, "quantity": 1}],
            },
            format="json",
        )
        assert response.status_code == 201

    def test_public_order_notifies_the_seller(self, api, shop):
        api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "Nasrin", "phone": "01911223344",
                "district": "Dhaka", "address_line": "House 9",
                "items": [{"product": shop["product"].id, "quantity": 1}],
            },
            format="json",
        )

        assert Notification.objects.for_store(shop["store"]).filter(
            notification_type=NotificationType.NEW_PUBLIC_ORDER
        ).exists()

    def test_blacklisted_customer_is_refused(self, api, shop):
        Customer.objects.create(
            store=shop["store"], name="Bad", phone="01911223344",
            is_blacklisted=True, blacklist_reason="Fake orders",
        )

        response = api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "Bad", "phone": "01911223344",
                "district": "Dhaka", "address_line": "House 9",
                "items": [{"product": shop["product"].id, "quantity": 1}],
            },
            format="json",
        )
        assert response.status_code == 403

    def test_product_from_another_store_is_rejected(
        self, api, shop, make_user, make_store
    ):
        stranger = make_store(make_user(email="bob@example.com"), name="Bob")
        foreign = Product.objects.create(
            store=stranger, name="Bob Item", selling_price=Decimal("100")
        )

        response = api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "X", "phone": "01911223344",
                "district": "Dhaka", "address_line": "House 9",
                "items": [{"product": foreign.id, "quantity": 1}],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_invalid_phone_rejected(self, api, shop):
        response = api.post(
            f"/api/v1/public/stores/{shop['store'].slug}/orders/",
            {
                "name": "X", "phone": "12345",
                "district": "Dhaka", "address_line": "House 9",
                "items": [{"product": shop["product"].id, "quantity": 1}],
            },
            format="json",
        )
        assert response.status_code == 400


class TestBilling:
    def test_plans_are_seeded(self):
        codes = set(Plan.objects.values_list("code", flat=True))
        assert {"free", "starter", "growth", "business"} <= codes

    def test_new_store_gets_the_free_plan(self, shop):
        subscription = get_or_create_subscription(shop["store"])

        assert subscription.plan.code == "free"
        assert subscription.plan.order_limit == 50

    def test_creating_an_order_counts_usage(self, shop):
        make_order(shop)
        subscription = get_or_create_subscription(shop["store"])

        assert subscription.orders_used == 1

    def test_order_cap_blocks_creation(self, shop):
        subscription = get_or_create_subscription(shop["store"])
        Subscription.objects.filter(pk=subscription.pk).update(orders_used=50)

        with pytest.raises(PlanLimitReached) as exc:
            make_order(shop)

        assert exc.value.code == "PLAN_LIMIT_REACHED"
        assert exc.value.status_code == 402

    def test_under_the_cap_still_works(self, shop):
        subscription = get_or_create_subscription(shop["store"])
        Subscription.objects.filter(pk=subscription.pk).update(orders_used=49)

        order = make_order(shop)
        assert order.pk is not None

    def test_usage_percent_and_warning(self, shop):
        subscription = get_or_create_subscription(shop["store"])
        Subscription.objects.filter(pk=subscription.pk).update(orders_used=40)
        subscription.refresh_from_db()

        assert subscription.usage_percent == Decimal("80.00")
        assert subscription.is_near_limit is True

    def test_unlimited_plan_never_blocks(self, shop):
        business = Plan.objects.get(code="business")
        activate_plan(shop["store"], business, actor=shop["owner"])

        subscription = get_or_create_subscription(shop["store"])
        Subscription.objects.filter(pk=subscription.pk).update(
            orders_used=99999
        )

        assert check_order_allowance(shop["store"]) is not None

    def test_activation_resets_usage(self, shop):
        subscription = get_or_create_subscription(shop["store"])
        Subscription.objects.filter(pk=subscription.pk).update(orders_used=40)

        starter = Plan.objects.get(code="starter")
        updated = activate_plan(
            shop["store"], starter, actor=shop["owner"], reference="BKASH-1"
        )

        assert updated.plan.code == "starter"
        assert updated.orders_used == 0
        assert updated.payment_reference == "BKASH-1"

    def test_period_rolls_over_and_resets_usage(self, shop):
        from datetime import timedelta

        from django.utils import timezone

        subscription = get_or_create_subscription(shop["store"])
        past = timezone.localdate() - timedelta(days=5)
        Subscription.objects.filter(pk=subscription.pk).update(
            orders_used=50, period_end=past
        )

        refreshed = get_or_create_subscription(shop["store"])
        assert refreshed.orders_used == 0

    def test_usage_summary_shape(self, shop):
        summary = usage_summary(shop["store"])

        assert summary["plan"]["code"] == "free"
        assert summary["orders_remaining"] == 50
        assert summary["is_over_limit"] is False


class TestBillingEndpoints:
    def test_lists_plans(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BILLING}plans/"
        )

        assert response.status_code == 200
        codes = {row["code"] for row in response.data}
        assert "free" in codes

    def test_subscription_endpoint(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).get(
            f"{BILLING}subscription/"
        )

        assert response.status_code == 200
        assert response.data["plan"]["code"] == "free"

    def test_owner_can_activate_a_plan(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            f"{BILLING}activate/",
            {"plan": "starter", "reference": "BKASH-99"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["plan"]["code"] == "starter"

    def test_manager_cannot_activate(
        self, shop, auth, make_user, make_member
    ):
        manager = make_user(email="manager@example.com")
        make_member(shop["store"], manager, StoreRole.MANAGER)

        response = auth(manager, store=shop["store"]).post(
            f"{BILLING}activate/", {"plan": "starter"}, format="json"
        )
        assert response.status_code == 403

    def test_unknown_plan_rejected(self, shop, auth):
        response = auth(shop["owner"], store=shop["store"]).post(
            f"{BILLING}activate/", {"plan": "platinum"}, format="json"
        )
        assert response.status_code == 400
