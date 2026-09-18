"""
Role capabilities and DRF permission classes (PRD §6.1).

The matrix below is the single place the permission table lives. Views
declare the capability they need; they never test role strings inline,
so adding a role means editing one dict rather than hunting call sites.
"""
from rest_framework import permissions

from .models import StoreRole


class Cap:
    """Capability constants. Names mirror the PRD permission matrix rows."""

    VIEW_ORDERS = "view_orders"
    MANAGE_ORDERS = "manage_orders"          # create / edit
    CONFIRM_ORDERS = "confirm_orders"        # confirm / cancel
    BOOK_SHIPMENTS = "book_shipments"
    UPDATE_SHIPMENT_STATUS = "update_shipment_status"
    RECORD_RETURNS = "record_returns"

    VIEW_PRODUCTS = "view_products"
    MANAGE_PRODUCTS = "manage_products"
    VIEW_COST_PRICE = "view_cost_price"      # cost & margin

    VIEW_CUSTOMERS = "view_customers"
    MANAGE_CUSTOMERS = "manage_customers"
    EXPORT_CUSTOMERS = "export_customers"

    RECORD_PAYMENTS = "record_payments"
    RECONCILE_COD = "reconcile_cod"
    MANAGE_EXPENSES = "manage_expenses"
    VIEW_ANALYTICS = "view_analytics"        # includes profit

    MANAGE_STAFF = "manage_staff"
    MANAGE_COURIER_CREDENTIALS = "manage_courier_credentials"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_BILLING = "manage_billing"
    DELETE_STORE = "delete_store"


#: Capability -> set of roles that hold it. Mirrors PRD §6.1 exactly.
ROLE_CAPABILITIES = {
    Cap.VIEW_ORDERS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
        StoreRole.DELIVERY_STAFF, StoreRole.ACCOUNTANT,
    },
    Cap.MANAGE_ORDERS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
    },
    Cap.CONFIRM_ORDERS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
    },
    Cap.BOOK_SHIPMENTS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
    },
    Cap.UPDATE_SHIPMENT_STATUS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
        StoreRole.DELIVERY_STAFF,
    },
    Cap.RECORD_RETURNS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
        StoreRole.DELIVERY_STAFF,
    },

    Cap.VIEW_PRODUCTS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
    },
    Cap.MANAGE_PRODUCTS: {StoreRole.OWNER, StoreRole.MANAGER},
    Cap.VIEW_COST_PRICE: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ACCOUNTANT,
    },

    Cap.VIEW_CUSTOMERS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
        StoreRole.DELIVERY_STAFF, StoreRole.ACCOUNTANT,
    },
    Cap.MANAGE_CUSTOMERS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ORDER_STAFF,
    },
    Cap.EXPORT_CUSTOMERS: {StoreRole.OWNER, StoreRole.MANAGER},

    Cap.RECORD_PAYMENTS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ACCOUNTANT,
    },
    Cap.RECONCILE_COD: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ACCOUNTANT,
    },
    Cap.MANAGE_EXPENSES: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ACCOUNTANT,
    },
    Cap.VIEW_ANALYTICS: {
        StoreRole.OWNER, StoreRole.MANAGER, StoreRole.ACCOUNTANT,
    },

    Cap.MANAGE_STAFF: {StoreRole.OWNER},
    Cap.MANAGE_COURIER_CREDENTIALS: {StoreRole.OWNER},
    Cap.MANAGE_SETTINGS: {StoreRole.OWNER, StoreRole.MANAGER},
    Cap.MANAGE_BILLING: {StoreRole.OWNER},
    Cap.DELETE_STORE: {StoreRole.OWNER},
}


def role_has(role, capability):
    """True if `role` holds `capability`."""
    return role in ROLE_CAPABILITIES.get(capability, set())


def capabilities_for(role):
    """Every capability held by `role` — handy for the frontend to gate UI."""
    return sorted(
        cap for cap, roles in ROLE_CAPABILITIES.items() if role in roles
    )


class IsStoreMember(permissions.BasePermission):
    """
    Caller must hold an active membership for the resolved store.

    `request.store` and `request.membership` are set by StoreContextMixin
    before this runs.
    """

    message = "You do not have access to this store."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and membership.is_active


class HasStoreCapability(permissions.BasePermission):
    """
    Checks the capability named by `view.required_capability`.

    A view may instead define `capability_map = {"POST": Cap.X, ...}` to
    vary the requirement by HTTP method — the common case where reading
    is broadly allowed but writing is not.
    """

    message = "Your role does not permit this action."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None or not membership.is_active:
            return False

        capability = self._required(request, view)
        if capability is None:
            return True
        return role_has(membership.role, capability)

    @staticmethod
    def _required(request, view):
        cap_map = getattr(view, "capability_map", None)
        if cap_map:
            if request.method in cap_map:
                return cap_map[request.method]
            if request.method in permissions.SAFE_METHODS and "GET" in cap_map:
                return cap_map["GET"]
        return getattr(view, "required_capability", None)


class IsStoreOwner(permissions.BasePermission):
    """Owner-only actions (billing, staff management, store deletion)."""

    message = "Only the store owner can do this."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and membership.is_owner
