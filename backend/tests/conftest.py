"""Shared fixtures."""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.stores.models import Store, StoreMembership, StoreRole, StoreSettings


@pytest.fixture(autouse=True)
def reset_throttles():
    """
    Clear DRF throttle counters between tests.

    Throttle state lives in the cache and is not part of the database
    rollback, so without this a test's rate-limit consumption leaks into
    later tests and they fail with 429 depending on run order.
    """
    cache.clear()
    yield
    cache.clear()

@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email="seller@example.com", password="Str0ngPass!23", **extra):
        extra.setdefault("full_name", "Test Seller")
        return User.objects.create_user(email=email, password=password, **extra)

    return _make


@pytest.fixture
def make_store(db):
    def _make(owner, name="Test Store", **extra):
        store = Store.objects.create(owner=owner, name=name, **extra)
        StoreSettings.objects.create(store=store)
        StoreMembership.objects.create(
            store=store, user=owner, role=StoreRole.OWNER
        )
        return store

    return _make


@pytest.fixture
def make_member(db):
    def _make(store, user, role=StoreRole.ORDER_STAFF):
        return StoreMembership.objects.create(store=store, user=user, role=role)

    return _make


@pytest.fixture
def auth(api):
    """Authenticate the client as `user`, optionally scoped to `store`."""

    def _auth(user, store=None):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user).access_token
        credentials = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        if store is not None:
            credentials["HTTP_X_STORE_ID"] = str(store.id)
        api.credentials(**credentials)
        return api

    return _auth


@pytest.fixture
def two_stores(make_user, make_store):
    """
    Two unrelated sellers with their own stores.

    The backbone of the isolation tests: anything one can see of the
    other's data is a tenancy bug.
    """
    alice = make_user(email="alice@example.com", full_name="Alice")
    bob = make_user(email="bob@example.com", full_name="Bob")
    store_a = make_store(alice, name="Alice Fashion")
    store_b = make_store(bob, name="Bob Electronics")
    return {
        "alice": alice, "bob": bob,
        "store_a": store_a, "store_b": store_b,
    }
