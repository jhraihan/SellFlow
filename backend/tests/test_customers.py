from decimal import Decimal

import pytest

from apps.customers.models import Customer, CustomerAddress, RiskLevel
from apps.stores.models import StoreRole

pytestmark = pytest.mark.django_db

CUSTOMERS = "/api/v1/customers/"
LOOKUP = "/api/v1/customers/lookup/"


@pytest.fixture
def owner_store(make_user, make_store):
    owner = make_user(email="owner@example.com")
    return owner, make_store(owner)


class TestCustomerCreation:
    def test_creates_customer_with_address(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            CUSTOMERS,
            {
                "name": "Karim Ahmed",
                "phone": "01712345678",
                "address": {
                    "district": "Dhaka",
                    "thana": "Dhanmondi",
                    "address_line": "House 12, Road 4",
                },
            },
            format="json",
        )

        assert response.status_code == 201
        customer = Customer.objects.get(id=response.data["id"])
        assert customer.addresses.count() == 1
        assert customer.addresses.first().is_default is True

    def test_phone_is_normalised(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            CUSTOMERS, {"name": "Karim", "phone": "01712345678"}, format="json"
        )

        assert response.data["phone"] == "+8801712345678"

    @pytest.mark.parametrize(
        "raw", ["01712345678", "+8801712345678", "8801712345678"]
    )
    def test_same_number_any_format_is_a_duplicate(
        self, owner_store, auth, raw
    ):
        owner, store = owner_store
        Customer.objects.create(
            store=store, name="Existing", phone="01712345678"
        )

        response = auth(owner, store=store).post(
            CUSTOMERS, {"name": "Karim", "phone": raw}, format="json"
        )
        assert response.status_code == 400

    def test_invalid_phone_rejected(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).post(
            CUSTOMERS, {"name": "Karim", "phone": "12345"}, format="json"
        )
        assert response.status_code == 400

    def test_same_phone_allowed_across_stores(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        body = {"name": "Karim", "phone": "01712345678"}
        first = auth(alice, store=store_a).post(CUSTOMERS, body, format="json")
        second = auth(bob, store=store_b).post(CUSTOMERS, body, format="json")

        assert first.status_code == 201
        assert second.status_code == 201


class TestCustomerLookup:
    def test_finds_customer_by_any_phone_format(self, owner_store, auth):
        owner, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )
        CustomerAddress.objects.create(
            store=store, customer=customer, district="Dhaka",
            address_line="House 12", is_default=True,
        )

        response = auth(owner, store=store).get(
            f"{LOOKUP}?phone=%2B8801712345678"
        )

        assert response.status_code == 200
        assert response.data["found"] is True
        assert response.data["customer"]["name"] == "Karim"
        assert response.data["customer"]["default_address"]["district"] == "Dhaka"

    def test_reports_not_found_without_error(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).get(f"{LOOKUP}?phone=01912345678")

        assert response.status_code == 200
        assert response.data["found"] is False
        assert response.data["customer"] is None

    def test_requires_a_phone_parameter(self, owner_store, auth):
        owner, store = owner_store
        response = auth(owner, store=store).get(LOOKUP)
        assert response.status_code == 400

    def test_does_not_find_another_stores_customer(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        Customer.objects.create(
            store=store_b, name="Bob Customer", phone="01712345678"
        )

        response = auth(alice, store=store_a).get(f"{LOOKUP}?phone=01712345678")
        assert response.data["found"] is False


class TestRiskScoring:
    def _customer(self, store, **counts):
        return Customer.objects.create(
            store=store, name="Karim", phone="01712345678", **counts
        )

    def test_new_customer_is_good(self, owner_store):
        _, store = owner_store
        customer = self._customer(store)

        assert customer.compute_risk_level() == RiskLevel.GOOD

    def test_return_rate_is_computed_over_shipped_orders(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=8, returned_count=2)

        assert customer.shipped_count == 10
        assert customer.return_rate == Decimal("20.00")
        assert customer.success_rate == Decimal("80.00")

    def test_cancelled_orders_do_not_affect_return_rate(self, owner_store):
        _, store = owner_store
        customer = self._customer(
            store, delivered_count=8, returned_count=2, cancelled_count=5
        )

        assert customer.return_rate == Decimal("20.00")

    def test_one_return_puts_customer_on_watch(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=9, returned_count=1)

        assert customer.compute_risk_level() == RiskLevel.WATCH

    def test_return_count_threshold_triggers_high_risk(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=20, returned_count=3)

        assert customer.compute_risk_level() == RiskLevel.HIGH_RISK

    def test_return_rate_threshold_triggers_high_risk(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=1, returned_count=1)

        assert customer.return_rate == Decimal("50.00")
        assert customer.compute_risk_level() == RiskLevel.HIGH_RISK

    def test_store_thresholds_are_honoured(self, owner_store):
        _, store = owner_store
        settings = store.settings
        settings.fraud_return_count_threshold = 10
        settings.fraud_return_rate_threshold = Decimal("90.00")
        settings.save()

        customer = self._customer(store, delivered_count=7, returned_count=3)

        assert customer.compute_risk_level(settings) == RiskLevel.WATCH

    def test_blacklist_overrides_computed_level(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=50, returned_count=0)
        customer.is_blacklisted = True
        customer.save()

        assert customer.risk_level == RiskLevel.BLACKLISTED

    def test_refresh_persists_the_new_level(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, delivered_count=1, returned_count=1)

        customer.refresh_risk_level()
        customer.refresh_from_db()

        assert customer.risk_level == RiskLevel.HIGH_RISK

    def test_zero_shipped_never_divides_by_zero(self, owner_store):
        _, store = owner_store
        customer = self._customer(store, cancelled_count=5)

        assert customer.return_rate == Decimal("0.00")
        assert customer.compute_risk_level() == RiskLevel.GOOD


class TestBlacklisting:
    def test_owner_can_blacklist(self, owner_store, auth):
        owner, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )

        response = auth(owner, store=store).post(
            f"{CUSTOMERS}{customer.id}/blacklist/",
            {"is_blacklisted": True, "reason": "Repeated fake orders"},
            format="json",
        )

        assert response.status_code == 200
        customer.refresh_from_db()
        assert customer.is_blacklisted is True
        assert customer.risk_level == RiskLevel.BLACKLISTED

    def test_blacklisting_requires_a_reason(self, owner_store, auth):
        owner, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )

        response = auth(owner, store=store).post(
            f"{CUSTOMERS}{customer.id}/blacklist/",
            {"is_blacklisted": True},
            format="json",
        )
        assert response.status_code == 400

    def test_unblacklisting_recomputes_risk(self, owner_store, auth):
        owner, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678",
            delivered_count=10, returned_count=0,
            is_blacklisted=True, blacklist_reason="Mistake",
        )

        response = auth(owner, store=store).post(
            f"{CUSTOMERS}{customer.id}/blacklist/",
            {"is_blacklisted": False},
            format="json",
        )

        assert response.status_code == 200
        customer.refresh_from_db()
        assert customer.is_blacklisted is False
        assert customer.risk_level == RiskLevel.GOOD


class TestAddresses:
    def test_setting_a_new_default_unsets_the_old_one(self, owner_store):
        _, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )
        first = CustomerAddress.objects.create(
            store=store, customer=customer, district="Dhaka",
            address_line="Old address", is_default=True,
        )
        second = CustomerAddress.objects.create(
            store=store, customer=customer, district="Dhaka",
            address_line="New address", is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.is_default is False
        assert second.is_default is True

    def test_add_address_via_endpoint(self, owner_store, auth):
        owner, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )

        response = auth(owner, store=store).post(
            f"{CUSTOMERS}{customer.id}/addresses/",
            {"district": "Chattogram", "address_line": "Flat 3B",
             "is_default": True},
            format="json",
        )

        assert response.status_code == 201
        assert customer.addresses.count() == 1

    def test_full_address_joins_the_parts(self, owner_store):
        _, store = owner_store
        customer = Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )
        address = CustomerAddress.objects.create(
            store=store, customer=customer, district="Dhaka",
            thana="Dhanmondi", area="Road 4", address_line="House 12",
        )

        assert address.full_address == "House 12, Road 4, Dhanmondi, Dhaka"


class TestCustomerPermissions:
    def test_order_staff_can_manage_customers(
        self, owner_store, make_user, make_member, auth
    ):
        owner, store = owner_store
        staff = make_user(email="staff@example.com")
        make_member(store, staff, StoreRole.ORDER_STAFF)

        response = auth(staff, store=store).post(
            CUSTOMERS, {"name": "Karim", "phone": "01712345678"}, format="json"
        )
        assert response.status_code == 201

    def test_delivery_staff_cannot_create_customers(
        self, owner_store, make_user, make_member, auth
    ):
        owner, store = owner_store
        rider = make_user(email="rider@example.com")
        make_member(store, rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=store).post(
            CUSTOMERS, {"name": "Karim", "phone": "01712345678"}, format="json"
        )
        assert response.status_code == 403

    def test_delivery_staff_can_view_customers(
        self, owner_store, make_user, make_member, auth
    ):
        owner, store = owner_store
        Customer.objects.create(
            store=store, name="Karim", phone="01712345678"
        )
        rider = make_user(email="rider@example.com")
        make_member(store, rider, StoreRole.DELIVERY_STAFF)

        response = auth(rider, store=store).get(CUSTOMERS)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1


class TestCustomerTenancy:
    def test_list_is_scoped_to_the_store(self, make_user, make_store, auth):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        Customer.objects.create(
            store=store_a, name="Alice Customer", phone="01712345678"
        )
        Customer.objects.create(
            store=store_b, name="Bob Customer", phone="01812345678"
        )

        response = auth(alice, store=store_a).get(CUSTOMERS)
        names = {r["name"] for r in response.data["results"]}
        assert names == {"Alice Customer"}

    def test_cannot_read_another_stores_customer(
        self, make_user, make_store, auth
    ):
        alice = make_user(email="alice@example.com")
        bob = make_user(email="bob@example.com")
        store_a = make_store(alice, name="Alice Store")
        store_b = make_store(bob, name="Bob Store")

        foreign = Customer.objects.create(
            store=store_b, name="Bob Customer", phone="01812345678"
        )

        response = auth(alice, store=store_a).get(f"{CUSTOMERS}{foreign.id}/")
        assert response.status_code == 404
