from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tokens import issue_reset_token
from apps.catalog.models import Product
from apps.catalog.services import get_or_create_stock_item, receive_stock
from apps.couriers.models import Courier, StoreCourier
from apps.customers.models import Customer
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition_status
from apps.shipments.services import book_shipment

pytestmark = pytest.mark.django_db

RESET = "/api/v1/auth/password/reset/"
RESET_CONFIRM = "/api/v1/auth/password/reset/confirm/"
VERIFY_SEND = "/api/v1/auth/email/verify/send/"
VERIFY = "/api/v1/auth/email/verify/"
TRACK = "/api/v1/public/track/"
GOOD_PASSWORD = "Str0ngPass!23"
NEW_PASSWORD = "Even5tronger!99"

_n = {"i": 0}


@pytest.fixture
def shop(make_user, make_store):
    owner = make_user(email="owner@example.com", password=GOOD_PASSWORD)
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


def make_order(shop, quantity=2):
    return create_order(
        shop["store"],
        customer=shop["customer"],
        items=[{"product": shop["product"], "quantity": quantity}],
        shipping={
            "district": "Dhaka", "thana": "Dhanmondi",
            "address_line": "House 12, Road 4",
        },
        actor=shop["owner"],
    )


def shipped(shop, quantity=1):
    _n["i"] += 1
    order = make_order(shop, quantity)
    order = transition_status(order, OrderStatus.CONFIRMED)
    shipment = book_shipment(
        order, shop["courier"], actor=shop["owner"],
        manual_consignment_id=f"TRACK-{_n['i']:04d}",
    )
    order.refresh_from_db()
    return order, shipment


class TestPasswordReset:
    def test_request_sends_an_email(self, api, shop):
        mail.outbox.clear()

        response = api.post(
            RESET, {"email": "owner@example.com"}, format="json"
        )

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "reset-password" in mail.outbox[0].body

    def test_unknown_email_does_not_reveal_anything(self, api, shop):
        mail.outbox.clear()

        response = api.post(
            RESET, {"email": "nobody@example.com"}, format="json"
        )

        assert response.status_code == 200
        assert len(mail.outbox) == 0

    def test_token_resets_the_password(self, api, shop):
        token = issue_reset_token(shop["owner"])

        response = api.post(
            RESET_CONFIRM,
            {"token": token, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        shop["owner"].refresh_from_db()
        assert shop["owner"].check_password(NEW_PASSWORD)

    def test_token_cannot_be_reused(self, api, shop):
        token = issue_reset_token(shop["owner"])
        body = {"token": token, "new_password": NEW_PASSWORD}

        assert api.post(RESET_CONFIRM, body, format="json").status_code == 200
        second = api.post(RESET_CONFIRM, body, format="json")

        assert second.status_code == 400
        assert second.data["error"]["code"] == "INVALID_RESET_TOKEN"

    def test_unknown_token_rejected(self, api, shop):
        response = api.post(
            RESET_CONFIRM,
            {"token": "not-real", "new_password": NEW_PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_weak_password_rejected(self, api, shop):
        token = issue_reset_token(shop["owner"])

        response = api.post(
            RESET_CONFIRM,
            {"token": token, "new_password": "12345678"},
            format="json",
        )
        assert response.status_code == 400

    def test_reset_revokes_existing_sessions(self, api, shop):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = str(RefreshToken.for_user(shop["owner"]))
        token = issue_reset_token(shop["owner"])

        api.post(
            RESET_CONFIRM,
            {"token": token, "new_password": NEW_PASSWORD},
            format="json",
        )

        response = api.post(
            "/api/v1/auth/refresh/", {"refresh": refresh}, format="json"
        )
        assert response.status_code == 401

    def test_old_password_stops_working(self, api, shop):
        token = issue_reset_token(shop["owner"])
        api.post(
            RESET_CONFIRM,
            {"token": token, "new_password": NEW_PASSWORD},
            format="json",
        )

        response = api.post(
            "/api/v1/auth/login/",
            {"email": "owner@example.com", "password": GOOD_PASSWORD},
            format="json",
        )
        assert response.status_code == 401


class TestEmailVerification:
    def test_send_then_verify(self, api, shop, auth):
        mail.outbox.clear()
        client = auth(shop["owner"], store=shop["store"])

        sent = client.post(VERIFY_SEND, {}, format="json")
        assert sent.status_code == 200
        assert len(mail.outbox) == 1

        body = mail.outbox[0].body
        token = body.split("verify-email/")[1].split()[0]

        response = api.post(VERIFY, {"token": token}, format="json")

        assert response.status_code == 200
        shop["owner"].refresh_from_db()
        assert shop["owner"].is_email_verified

    def test_already_verified_is_a_no_op(self, shop, auth):
        shop["owner"].email_verified_at = timezone.now()
        shop["owner"].save()

        response = auth(shop["owner"], store=shop["store"]).post(
            VERIFY_SEND, {}, format="json"
        )
        assert response.status_code == 200
        assert "already verified" in response.data["detail"]

    def test_bad_token_rejected(self, api, shop):
        response = api.post(VERIFY, {"token": "nope"}, format="json")

        assert response.status_code == 400
        assert response.data["error"]["code"] == "INVALID_VERIFICATION_TOKEN"


class TestPublicTracking:
    def test_finds_order_by_consignment(self, api, shop):
        order, shipment = shipped(shop)

        response = api.get(f"{TRACK}?code={shipment.consignment_id}")

        assert response.status_code == 200
        assert response.data["found"] is True
        assert response.data["order_number"] == order.order_number
        assert response.data["status"] == OrderStatus.SHIPPED

    def test_finds_order_by_number_and_phone(self, api, shop):
        order, _ = shipped(shop)

        response = api.get(
            f"{TRACK}?order_number={order.order_number}&phone=01712345678"
        )

        assert response.status_code == 200
        assert response.data["found"] is True

    def test_wrong_phone_finds_nothing(self, api, shop):
        order, _ = shipped(shop)

        response = api.get(
            f"{TRACK}?order_number={order.order_number}&phone=01999999999"
        )
        assert response.status_code == 404

    def test_unknown_code_returns_404(self, api, shop):
        response = api.get(f"{TRACK}?code=GHOST-1")
        assert response.status_code == 404

    def test_missing_input_is_rejected(self, api, shop):
        response = api.get(TRACK)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "TRACKING_INPUT_REQUIRED"

    def test_needs_no_authentication(self, api, shop):
        order, shipment = shipped(shop)
        api.credentials()

        response = api.get(f"{TRACK}?code={shipment.consignment_id}")
        assert response.status_code == 200

    def test_phone_is_masked(self, api, shop):
        order, shipment = shipped(shop)

        response = api.get(f"{TRACK}?code={shipment.consignment_id}")
        phone = response.data["recipient_phone"]

        assert phone.endswith("5678")
        assert "+8801712" not in phone

    def test_no_money_or_address_is_exposed(self, api, shop):
        order, shipment = shipped(shop)

        response = api.get(f"{TRACK}?code={shipment.consignment_id}")
        body = str(response.data)

        for leaked in ("cod_amount", "total_amount", "House 12", "unit_cost"):
            assert leaked not in body

    def test_timeline_is_returned(self, api, shop):
        order, shipment = shipped(shop)

        response = api.get(f"{TRACK}?code={shipment.consignment_id}")
        statuses = [row["status"] for row in response.data["timeline"]]

        assert OrderStatus.PENDING in statuses
        assert OrderStatus.SHIPPED in statuses


class TestInvoiceAndLabel:
    def _client(self, shop, auth):
        return auth(shop["owner"], store=shop["store"])

    def test_invoice_returns_a_pdf(self, shop, auth):
        order = make_order(shop)

        response = self._client(shop, auth).get(
            f"/api/v1/orders/{order.id}/invoice/"
        )

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        content = b"".join(response.streaming_content)
        assert content.startswith(b"%PDF")

    def test_invoice_filename_uses_order_number(self, shop, auth):
        order = make_order(shop)

        response = self._client(shop, auth).get(
            f"/api/v1/orders/{order.id}/invoice/"
        )
        assert order.order_number in response["Content-Disposition"]

    def test_label_returns_a_pdf(self, shop, auth):
        order, _ = shipped(shop)

        response = self._client(shop, auth).get(
            f"/api/v1/orders/{order.id}/label/"
        )

        assert response.status_code == 200
        content = b"".join(response.streaming_content)
        assert content.startswith(b"%PDF")

    def test_label_works_before_a_shipment_exists(self, shop, auth):
        order = make_order(shop)

        response = self._client(shop, auth).get(
            f"/api/v1/orders/{order.id}/label/"
        )
        assert response.status_code == 200

    def test_cannot_print_another_stores_order(
        self, shop, auth, make_user, make_store
    ):
        order = make_order(shop)
        stranger = make_user(email="bob@example.com")
        other = make_store(stranger, name="Bob Store")

        response = auth(stranger, store=other).get(
            f"/api/v1/orders/{order.id}/invoice/"
        )
        assert response.status_code == 404

    def test_invoice_builds_with_variants_and_discount(self, shop, auth):
        from apps.catalog.models import ProductVariant

        parent = Product.objects.create(
            store=shop["store"], name="T-Shirt",
            selling_price=Decimal("550.00"), has_variants=True,
        )
        variant = ProductVariant.objects.create(
            store=shop["store"], product=parent,
            option1_name="Size", option1_value="XL",
        )
        receive_stock(get_or_create_stock_item(parent, variant), 10)

        order = create_order(
            shop["store"],
            customer=shop["customer"],
            items=[{"product": parent, "variant": variant, "quantity": 2}],
            shipping={"district": "Dhaka", "address_line": "House 12"},
            discount_amount=Decimal("50.00"),
            advance_paid=Decimal("100.00"),
            actor=shop["owner"],
        )

        response = self._client(shop, auth).get(
            f"/api/v1/orders/{order.id}/invoice/"
        )

        assert response.status_code == 200
        content = b"".join(response.streaming_content)
        assert len(content) > 1000
