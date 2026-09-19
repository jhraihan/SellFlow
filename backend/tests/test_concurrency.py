import threading
from decimal import Decimal

import pytest
from django.db import connection, connections, transaction

from apps.catalog.models import Product, StockItem
from apps.catalog.services import get_or_create_stock_item, receive_stock, reserve_stock
from apps.core.exceptions import InsufficientStock

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Row-level locking is a no-op on SQLite; run against PostgreSQL.",
)


@pytest.fixture
def stock(make_user, make_store):
    store = make_store(make_user())
    product = Product.objects.create(
        store=store,
        name="Cotton Kurti",
        selling_price=Decimal("1200.00"),
        low_stock_threshold=5,
    )
    item = get_or_create_stock_item(product, None)
    receive_stock(item, 10)
    item.refresh_from_db()
    return item


@pytest.mark.django_db(transaction=True)
@postgres_only
class TestConcurrentReservation:
    def test_two_threads_cannot_oversell(self, stock):
        barrier = threading.Barrier(2)
        results = []

        def worker():
            try:
                barrier.wait(timeout=10)
                reserve_stock(stock, 6)
                results.append("ok")
            except InsufficientStock:
                results.append("rejected")
            except Exception as exc:
                results.append(f"error:{exc}")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        stock.refresh_from_db()

        assert sorted(results) == ["ok", "rejected"], results
        assert stock.reserved == 6
        assert stock.available == 4

    def test_parallel_reservations_never_exceed_on_hand(self, stock):
        barrier = threading.Barrier(5)
        results = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait(timeout=10)
                reserve_stock(stock, 3)
                with lock:
                    results.append("ok")
            except InsufficientStock:
                with lock:
                    results.append("rejected")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        stock.refresh_from_db()

        assert results.count("ok") == 3
        assert results.count("rejected") == 2
        assert stock.reserved == 9
        assert stock.reserved <= stock.on_hand

    def test_concurrent_adjustments_do_not_clobber(self, stock):
        from apps.catalog.services import adjust_stock

        barrier = threading.Barrier(2)
        errors = []

        def worker(target):
            try:
                barrier.wait(timeout=10)
                adjust_stock(stock, target, reason="Stock count")
            except Exception as exc:
                errors.append(str(exc))
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=worker, args=(20,)),
            threading.Thread(target=worker, args=(30,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        stock.refresh_from_db()

        assert errors == []
        assert stock.on_hand in (20, 30)

        from apps.catalog.services import rebuild_stock_from_ledger

        rebuilt = rebuild_stock_from_ledger(stock)
        assert rebuilt["on_hand"] == stock.on_hand


@pytest.mark.django_db(transaction=True)
@postgres_only
def test_select_for_update_actually_locks(stock):
    acquired = threading.Event()
    blocked_until_release = threading.Event()
    observed = {}

    def holder():
        try:
            with transaction.atomic():
                StockItem.objects.select_for_update().get(pk=stock.pk)
                acquired.set()
                blocked_until_release.wait(timeout=5)
        finally:
            connections.close_all()

    def waiter():
        try:
            acquired.wait(timeout=5)
            with transaction.atomic():
                StockItem.objects.select_for_update().get(pk=stock.pk)
                observed["got_lock_while_held"] = not blocked_until_release.is_set()
        finally:
            connections.close_all()

    holder_thread = threading.Thread(target=holder)
    waiter_thread = threading.Thread(target=waiter)

    holder_thread.start()
    waiter_thread.start()

    acquired.wait(timeout=5)
    waiter_thread.join(timeout=2)
    still_blocked = waiter_thread.is_alive()

    blocked_until_release.set()
    holder_thread.join(timeout=5)
    waiter_thread.join(timeout=5)

    assert still_blocked, (
        "The second transaction was not blocked, so select_for_update is not "
        "taking a row lock on this database."
    )
