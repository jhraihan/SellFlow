from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import StockItem
from apps.catalog.services import (
    get_or_create_stock_item,
    release_reservation,
    reserve_stock,
    ship_stock,
)
from apps.core.exceptions import APIError, InvalidTransition
from apps.customers.models import Customer
from apps.stores.models import Store

from .models import (
    STOCK_RESERVED_FROM,
    CallOutcome,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
)


class OrderError(APIError):
    default_code = "ORDER_ERROR"
    default_detail = "Order operation failed."


class OrderNotEditable(OrderError):
    default_code = "ORDER_NOT_EDITABLE"
    default_detail = "This order can no longer be edited."


@transaction.atomic
def allocate_order_number(store):
    locked = Store.objects.select_for_update().get(pk=store.pk)
    locked.order_sequence = F("order_sequence") + 1
    locked.save(update_fields=["order_sequence", "updated_at"])
    locked.refresh_from_db(fields=["order_sequence"])
    return f"{locked.order_prefix}-{locked.order_sequence}"


def resolve_stock_item(product, variant):
    if variant is not None:
        item = StockItem.objects.filter(variant=variant).first()
    else:
        item = StockItem.objects.filter(
            product=product, variant__isnull=True
        ).first()
    if item is None:
        item = get_or_create_stock_item(product, variant)
    return item


def build_item_snapshot(store, row):
    product = row["product"]
    variant = row.get("variant")

    if product.store_id != store.id:
        raise OrderError("Unknown product.", code="UNKNOWN_PRODUCT")
    if variant is not None and variant.product_id != product.id:
        raise OrderError(
            "That variant does not belong to the product.",
            code="VARIANT_MISMATCH",
        )
    if product.has_variants and variant is None:
        raise OrderError(
            f"{product.name} requires a variant.", code="VARIANT_REQUIRED"
        )

    unit_price = row.get("unit_price")
    if unit_price is None:
        unit_price = variant.selling_price if variant else product.selling_price
    unit_cost = variant.cost_price if variant else product.cost_price

    return {
        "product": product,
        "variant": variant,
        "product_name": product.name,
        "variant_label": variant.label if variant else "",
        "sku": variant.sku if variant else product.sku,
        "unit_price": Decimal(str(unit_price)),
        "unit_cost": Decimal(str(unit_cost)),
        "quantity": row["quantity"],
    }


@transaction.atomic
def create_order(
    store,
    *,
    customer,
    items,
    shipping,
    source="manual",
    discount_amount=Decimal("0.00"),
    delivery_charge=None,
    advance_paid=Decimal("0.00"),
    internal_note="",
    customer_note="",
    actor=None,
):
    if not items:
        raise OrderError("An order needs at least one item.", code="NO_ITEMS")

    snapshots = [build_item_snapshot(store, row) for row in items]

    if delivery_charge is None:
        settings = getattr(store, "settings", None)
        district = shipping.get("district", "")
        if settings is not None:
            delivery_charge = settings.delivery_charge_for(district)
        else:
            delivery_charge = Decimal("0.00")
    delivery_charge = Decimal(str(delivery_charge))

    subtotal = sum(
        (s["unit_price"] * s["quantity"] for s in snapshots), Decimal("0.00")
    )
    discount_amount = Decimal(str(discount_amount))
    advance_paid = Decimal(str(advance_paid))

    if discount_amount > subtotal:
        raise OrderError(
            "The discount cannot be larger than the order subtotal.",
            code="DISCOUNT_TOO_LARGE",
            details={"subtotal": str(subtotal), "discount": str(discount_amount)},
        )

    settings = getattr(store, "settings", None)
    if settings is not None and settings.free_delivery_threshold is not None:
        if subtotal - discount_amount >= settings.free_delivery_threshold:
            delivery_charge = Decimal("0.00")

    total_amount = subtotal - discount_amount + delivery_charge

    if advance_paid > total_amount:
        raise OrderError(
            "The advance cannot be larger than the order total.",
            code="ADVANCE_TOO_LARGE",
            details={"total": str(total_amount), "advance": str(advance_paid)},
        )

    order = Order.objects.create(
        store=store,
        order_number=allocate_order_number(store),
        customer=customer,
        recipient_name=shipping.get("recipient_name") or customer.name,
        recipient_phone=shipping.get("recipient_phone") or customer.phone,
        shipping_district=shipping.get("district", ""),
        shipping_thana=shipping.get("thana", ""),
        shipping_area=shipping.get("area", ""),
        shipping_address=shipping.get("address_line", ""),
        source=source,
        discount_amount=discount_amount,
        delivery_charge=delivery_charge,
        advance_paid=advance_paid,
        internal_note=internal_note,
        customer_note=customer_note,
        created_by=actor,
    )

    OrderItem.objects.bulk_create(
        [OrderItem(order=order, **_item_fields(s)) for s in snapshots]
    )

    order.recalculate_totals(commit=True)

    OrderStatusHistory.objects.create(
        order=order,
        from_status="",
        to_status=OrderStatus.PENDING,
        note="Order created",
        actor=actor,
    )

    _touch_customer_on_create(customer)
    return order


def _item_fields(snapshot):
    fields = dict(snapshot)
    quantity = fields["quantity"]
    fields["line_total"] = fields["unit_price"] * quantity
    return fields


def _touch_customer_on_create(customer):
    Customer.objects.filter(pk=customer.pk).update(
        total_orders=F("total_orders") + 1,
        last_order_at=timezone.now(),
    )


@transaction.atomic
def transition_status(order, target, *, actor=None, note="", **kwargs):
    locked = Order.objects.select_for_update().get(pk=order.pk)
    current = locked.status

    if current == target:
        raise InvalidTransition(
            f"The order is already {locked.get_status_display()}.",
            details={"status": current},
        )

    if not locked.can_transition_to(target):
        raise InvalidTransition(
            f"Cannot move an order from {current} to {target}.",
            details={
                "from": current,
                "to": target,
                "allowed": locked.allowed_transitions(),
            },
        )

    if target == OrderStatus.CANCELLED and not kwargs.get("reason"):
        raise OrderError(
            "A reason is required to cancel an order.",
            code="CANCEL_REASON_REQUIRED",
        )

    _apply_side_effects(locked, current, target, actor=actor, **kwargs)

    locked.status = target
    _stamp_timestamp(locked, target)
    locked.save()

    OrderStatusHistory.objects.create(
        order=locked,
        from_status=current,
        to_status=target,
        note=note,
        actor=actor,
    )

    return locked


def _stamp_timestamp(order, target):
    now = timezone.now()
    stamps = {
        OrderStatus.CONFIRMED: "confirmed_at",
        OrderStatus.SHIPPED: "shipped_at",
        OrderStatus.DELIVERED: "delivered_at",
        OrderStatus.CANCELLED: "cancelled_at",
        OrderStatus.RETURNED: "returned_at",
    }
    field = stamps.get(target)
    if field and getattr(order, field) is None:
        setattr(order, field, now)


def _apply_side_effects(order, current, target, *, actor=None, **kwargs):
    was_reserved = current in STOCK_RESERVED_FROM
    will_reserve = target in STOCK_RESERVED_FROM

    if not was_reserved and will_reserve:
        _reserve_all(order, actor)

    elif was_reserved and target == OrderStatus.CANCELLED:
        _release_all(order, actor)

    elif was_reserved and target == OrderStatus.SHIPPED:
        _ship_all(order, actor)

    elif was_reserved and target == OrderStatus.ON_HOLD:
        _release_all(order, actor)

    if target == OrderStatus.CANCELLED:
        order.cancel_reason = kwargs.get("reason", "")
        order.cancel_note = kwargs.get("cancel_note", "")
        _decrement_customer_open(order, cancelled=True)

    if target == OrderStatus.DELIVERED:
        _mark_customer_delivered(order)

    if target == OrderStatus.RETURNED:
        _mark_customer_returned(order)


def _reserve_all(order, actor):
    for item in order.items.select_related("product", "variant"):
        stock_item = resolve_stock_item(item.product, item.variant)
        reserve_stock(
            stock_item, item.quantity, actor=actor, order_id=order.pk
        )


def _release_all(order, actor):
    for item in order.items.select_related("product", "variant"):
        stock_item = resolve_stock_item(item.product, item.variant)
        release_reservation(
            stock_item, item.quantity, actor=actor, order_id=order.pk
        )


def _ship_all(order, actor):
    for item in order.items.select_related("product", "variant"):
        stock_item = resolve_stock_item(item.product, item.variant)
        ship_stock(stock_item, item.quantity, actor=actor, order_id=order.pk)


def _mark_customer_delivered(order):
    Customer.objects.filter(pk=order.customer_id).update(
        delivered_count=F("delivered_count") + 1,
        lifetime_value=F("lifetime_value") + order.total_amount,
    )
    _refresh_customer_risk(order.customer_id, order.store)


def _mark_customer_returned(order):
    Customer.objects.filter(pk=order.customer_id).update(
        returned_count=F("returned_count") + 1
    )
    _refresh_customer_risk(order.customer_id, order.store)


def _decrement_customer_open(order, cancelled=False):
    if cancelled:
        Customer.objects.filter(pk=order.customer_id).update(
            cancelled_count=F("cancelled_count") + 1
        )


def _refresh_customer_risk(customer_id, store):
    customer = Customer.objects.filter(pk=customer_id).first()
    if customer is None:
        return
    customer.refresh_risk_level(getattr(store, "settings", None))


@transaction.atomic
def log_call(order, outcome, *, actor=None, note=""):
    locked = Order.objects.select_for_update().get(pk=order.pk)

    locked.confirmation_attempts = F("confirmation_attempts") + 1
    locked.last_call_outcome = outcome
    locked.last_call_at = timezone.now()
    locked.save(
        update_fields=[
            "confirmation_attempts",
            "last_call_outcome",
            "last_call_at",
            "updated_at",
        ]
    )
    locked.refresh_from_db(fields=["confirmation_attempts"])

    if outcome == CallOutcome.CONFIRMED:
        return transition_status(
            locked, OrderStatus.CONFIRMED, actor=actor, note=note or "Confirmed by call"
        )

    if outcome in (CallOutcome.CANCELLED, CallOutcome.FAKE):
        reason = (
            "fake_order" if outcome == CallOutcome.FAKE else "customer_cancelled"
        )
        return transition_status(
            locked,
            OrderStatus.CANCELLED,
            actor=actor,
            note=note,
            reason=reason,
        )

    return locked


@transaction.atomic
def update_items(order, items, *, actor=None):
    locked = Order.objects.select_for_update().get(pk=order.pk)

    if not locked.is_editable:
        raise OrderNotEditable(
            f"Items cannot be changed once an order is {locked.get_status_display()}.",
            details={"status": locked.status},
        )

    if not items:
        raise OrderError("An order needs at least one item.", code="NO_ITEMS")

    snapshots = [build_item_snapshot(locked.store, row) for row in items]

    if locked.has_reserved_stock:
        _release_all(locked, actor)

    locked.items.all().delete()
    OrderItem.objects.bulk_create(
        [OrderItem(order=locked, **_item_fields(s)) for s in snapshots]
    )

    if locked.has_reserved_stock:
        locked.refresh_from_db()
        _reserve_all(locked, actor)

    locked.recalculate_totals(commit=True)
    return locked


def find_duplicate_orders(store, customer, product_ids, within_hours=24):
    if customer is None:
        return Order.objects.none()

    cutoff = timezone.now() - timedelta(hours=within_hours)
    candidates = (
        Order.objects.filter(store=store, customer=customer, created_at__gte=cutoff)
        .open()
        .prefetch_related("items")
    )

    if not product_ids:
        return candidates

    wanted = set(product_ids)
    matches = [
        order
        for order in candidates
        if wanted & {item.product_id for item in order.items.all()}
    ]
    return matches


@transaction.atomic
def set_advance_payment(order, amount, *, actor=None):
    locked = Order.objects.select_for_update().get(pk=order.pk)
    amount = Decimal(str(amount))

    if amount < 0:
        raise OrderError("The advance cannot be negative.", code="INVALID_ADVANCE")
    if amount > locked.total_amount:
        raise OrderError(
            "The advance cannot be larger than the order total.",
            code="ADVANCE_TOO_LARGE",
            details={"total": str(locked.total_amount)},
        )

    locked.advance_paid = amount
    locked.recalculate_totals(commit=False)
    locked.save(
        update_fields=[
            "advance_paid",
            "cod_amount",
            "payment_status",
            "updated_at",
        ]
    )
    return locked
