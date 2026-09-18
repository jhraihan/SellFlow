import pytest

from apps.stores.models import StoreRole
from apps.stores.permissions import Cap, capabilities_for, role_has

pytestmark = pytest.mark.django_db

OWNER = StoreRole.OWNER
MANAGER = StoreRole.MANAGER
ORDER = StoreRole.ORDER_STAFF
DELIVERY = StoreRole.DELIVERY_STAFF
ACCOUNTANT = StoreRole.ACCOUNTANT

MATRIX = [
    (Cap.VIEW_ORDERS, {OWNER, MANAGER, ORDER, DELIVERY, ACCOUNTANT}),
    (Cap.MANAGE_ORDERS, {OWNER, MANAGER, ORDER}),
    (Cap.CONFIRM_ORDERS, {OWNER, MANAGER, ORDER}),
    (Cap.BOOK_SHIPMENTS, {OWNER, MANAGER, ORDER}),
    (Cap.UPDATE_SHIPMENT_STATUS, {OWNER, MANAGER, ORDER, DELIVERY}),
    (Cap.RECORD_RETURNS, {OWNER, MANAGER, ORDER, DELIVERY}),
    (Cap.VIEW_PRODUCTS, {OWNER, MANAGER, ORDER}),
    (Cap.MANAGE_PRODUCTS, {OWNER, MANAGER}),
    (Cap.VIEW_COST_PRICE, {OWNER, MANAGER, ACCOUNTANT}),
    (Cap.VIEW_CUSTOMERS, {OWNER, MANAGER, ORDER, DELIVERY, ACCOUNTANT}),
    (Cap.MANAGE_CUSTOMERS, {OWNER, MANAGER, ORDER}),
    (Cap.EXPORT_CUSTOMERS, {OWNER, MANAGER}),
    (Cap.RECORD_PAYMENTS, {OWNER, MANAGER, ACCOUNTANT}),
    (Cap.RECONCILE_COD, {OWNER, MANAGER, ACCOUNTANT}),
    (Cap.MANAGE_EXPENSES, {OWNER, MANAGER, ACCOUNTANT}),
    (Cap.VIEW_ANALYTICS, {OWNER, MANAGER, ACCOUNTANT}),
    (Cap.MANAGE_STAFF, {OWNER}),
    (Cap.MANAGE_COURIER_CREDENTIALS, {OWNER}),
    (Cap.MANAGE_SETTINGS, {OWNER, MANAGER}),
    (Cap.MANAGE_BILLING, {OWNER}),
    (Cap.DELETE_STORE, {OWNER}),
]

ALL_ROLES = {OWNER, MANAGER, ORDER, DELIVERY, ACCOUNTANT}


class TestCapabilityMatrix:
    @pytest.mark.parametrize("capability,holders", MATRIX)
    def test_matrix_row(self, capability, holders):
        for role in ALL_ROLES:
            expected = role in holders
            assert role_has(role, capability) is expected, (
                f"{role} should{'' if expected else ' not'} hold {capability}"
            )

    def test_owner_holds_every_capability(self):
        for capability, _ in MATRIX:
            assert role_has(OWNER, capability)

    def test_order_staff_cannot_see_cost_or_profit(self):
        assert not role_has(ORDER, Cap.VIEW_COST_PRICE)
        assert not role_has(ORDER, Cap.VIEW_ANALYTICS)

    def test_delivery_staff_cannot_export_customers(self):
        assert not role_has(DELIVERY, Cap.EXPORT_CUSTOMERS)

    def test_accountant_cannot_modify_orders(self):
        assert not role_has(ACCOUNTANT, Cap.MANAGE_ORDERS)
        assert not role_has(ACCOUNTANT, Cap.CONFIRM_ORDERS)

    def test_only_owner_manages_courier_credentials(self):
        for role in ALL_ROLES - {OWNER}:
            assert not role_has(role, Cap.MANAGE_COURIER_CREDENTIALS)

    def test_capabilities_for_is_consistent_with_role_has(self):
        for role in ALL_ROLES:
            for capability in capabilities_for(role):
                assert role_has(role, capability)

    def test_unknown_capability_is_denied(self):
        assert not role_has(OWNER, "no_such_capability")


class TestStaffEndpointEnforcement:

    @pytest.mark.parametrize(
        "role,expected",
        [
            (OWNER, 200),
            (MANAGER, 403),
            (ORDER, 403),
            (DELIVERY, 403),
            (ACCOUNTANT, 403),
        ],
    )
    def test_only_owner_lists_staff(
        self, role, expected, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)

        if role == OWNER:
            actor = owner
        else:
            actor = make_user(email=f"{role}@example.com")
            make_member(store, actor, role)

        response = auth(actor, store=store).get("/api/v1/stores/staff/")
        assert response.status_code == expected

    def test_non_member_is_denied(self, make_user, make_store, auth):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        stranger = make_user(email="stranger@example.com")

        response = auth(stranger, store=store).get("/api/v1/stores/staff/")
        assert response.status_code == 403

    def test_unauthenticated_is_rejected(self, api, make_user, make_store):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)

        response = api.get("/api/v1/stores/staff/", HTTP_X_STORE_ID=str(store.id))
        assert response.status_code == 401


class TestCapabilitiesEndpoint:
    def test_reports_role_and_capabilities(
        self, make_user, make_store, make_member, auth
    ):
        owner = make_user(email="owner@example.com")
        store = make_store(owner)
        staff = make_user(email="staff@example.com")
        make_member(store, staff, ORDER)

        response = auth(staff, store=store).get("/api/v1/stores/my-capabilities/")

        assert response.status_code == 200
        assert response.data["role"] == ORDER
        caps = response.data["capabilities"]
        assert Cap.MANAGE_ORDERS in caps
        assert Cap.VIEW_COST_PRICE not in caps
