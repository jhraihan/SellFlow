from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Notification, NotificationLevel, NotificationType

DEDUPE_WINDOW_HOURS = 24


@transaction.atomic
def notify(
    store,
    notification_type,
    title,
    *,
    body="",
    level=NotificationLevel.INFO,
    user=None,
    payload=None,
    link="",
    dedupe_key="",
    dedupe_hours=DEDUPE_WINDOW_HOURS,
):
    if dedupe_key:
        cutoff = timezone.now() - timedelta(hours=dedupe_hours)
        existing = Notification.objects.filter(
            store=store,
            dedupe_key=dedupe_key,
            created_at__gte=cutoff,
        ).first()
        if existing is not None:
            return existing

    return Notification.objects.create(
        store=store,
        user=user,
        notification_type=notification_type,
        level=level,
        title=title,
        body=body,
        payload=payload or {},
        link=link,
        dedupe_key=dedupe_key,
    )


def notify_public_order(order):
    return notify(
        order.store,
        NotificationType.NEW_PUBLIC_ORDER,
        f"New order {order.order_number}",
        body=f"{order.recipient_name} ordered Tk {order.total_amount}.",
        level=NotificationLevel.INFO,
        payload={"order_id": order.id},
        link=f"/orders/{order.id}",
        dedupe_key=f"public-order:{order.id}",
    )


def notify_booking_failed(order, courier_name, message):
    return notify(
        order.store,
        NotificationType.BOOKING_FAILED,
        f"Courier booking failed for {order.order_number}",
        body=f"{courier_name}: {message}"[:400],
        level=NotificationLevel.CRITICAL,
        payload={"order_id": order.id},
        link=f"/orders/{order.id}",
        dedupe_key=f"booking-failed:{order.id}",
        dedupe_hours=1,
    )


def notify_return(return_record):
    order = return_record.order
    return notify(
        return_record.store,
        NotificationType.RETURN_RECORDED,
        f"Return opened for {order.order_number}",
        body=(
            f"{return_record.get_reason_display()} - "
            f"Tk {return_record.total_loss} at risk."
        ),
        level=NotificationLevel.WARNING,
        payload={"return_id": return_record.id, "order_id": order.id},
        link=f"/returns/{return_record.id}",
        dedupe_key=f"return:{return_record.id}",
    )


def scan_low_stock(store, limit=25):
    from apps.catalog.models import StockItem

    created = []
    items = (
        StockItem.objects.for_store(store)
        .select_related("product", "variant")
        .filter(on_hand__lte=F("product__low_stock_threshold"))[:limit]
    )

    for item in items:
        label = item.product.name
        if item.variant:
            label = f"{label} ({item.variant.label})"

        created.append(
            notify(
                store,
                NotificationType.LOW_STOCK,
                f"Low stock: {label}",
                body=(
                    f"{item.available} left, threshold is "
                    f"{item.product.low_stock_threshold}."
                ),
                level=NotificationLevel.WARNING,
                payload={
                    "product_id": item.product_id,
                    "stock_item_id": item.id,
                    "available": item.available,
                },
                link=f"/products/{item.product_id}",
                dedupe_key=f"low-stock:{item.id}",
            )
        )
    return created


def scan_overdue_cod(store):
    from apps.shipments.models import CodStatus, Shipment

    settings = getattr(store, "settings", None)
    overdue_days = getattr(settings, "cod_overdue_days", 7)
    cutoff = timezone.now() - timedelta(days=overdue_days)

    overdue = Shipment.objects.for_store(store).filter(
        cod_status__in=[CodStatus.PENDING, CodStatus.COLLECTED],
        delivered_at__lt=cutoff,
        cancelled_at__isnull=True,
    )

    count = overdue.count()
    if count == 0:
        return None

    total = sum(shipment.cod_amount for shipment in overdue)
    return notify(
        store,
        NotificationType.COD_OVERDUE,
        f"{count} shipment(s) with COD overdue",
        body=(
            f"Tk {total} delivered more than {overdue_days} days ago and "
            "still not settled."
        ),
        level=NotificationLevel.CRITICAL,
        payload={"count": count, "amount": str(total)},
        link="/payments/cod-ledger",
        dedupe_key=f"cod-overdue:{store.id}",
    )


def run_all_scans(store=None):
    from apps.stores.models import Store

    stores = [store] if store is not None else Store.objects.filter(
        is_active=True
    )

    summary = {"low_stock": 0, "cod_overdue": 0, "stores": 0}
    for current in stores:
        summary["stores"] += 1
        summary["low_stock"] += len(scan_low_stock(current))
        if scan_overdue_cod(current) is not None:
            summary["cod_overdue"] += 1
    return summary
