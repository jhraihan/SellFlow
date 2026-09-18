from django.db import transaction

from apps.core.exceptions import APIError, InsufficientStock

from .models import MovementType, StockItem, StockMovement


class StockError(APIError):
    default_code = "STOCK_ERROR"
    default_detail = "Stock operation failed."


def get_or_create_stock_item(product, variant=None):
    item, _ = StockItem.objects.get_or_create(
        product=product,
        variant=variant,
        defaults={"store_id": product.store_id},
    )
    return item


@transaction.atomic
def record_movement(
    stock_item,
    movement_type,
    quantity,
    *,
    actor=None,
    reason="",
    reference_type="",
    reference_id=None,
    affects="on_hand",
):
    locked = StockItem.objects.select_for_update().get(pk=stock_item.pk)

    if affects == "on_hand":
        new_on_hand = locked.on_hand + quantity
        new_reserved = locked.reserved
        if new_on_hand < 0:
            raise InsufficientStock(
                "Not enough stock on hand.",
                details={
                    "stock_item": locked.pk,
                    "requested": abs(quantity),
                    "on_hand": locked.on_hand,
                },
            )
    elif affects == "reserved":
        new_on_hand = locked.on_hand
        new_reserved = locked.reserved + quantity
        if new_reserved < 0:
            raise StockError(
                "Cannot release more than is reserved.",
                details={
                    "stock_item": locked.pk,
                    "requested": abs(quantity),
                    "reserved": locked.reserved,
                },
            )
        if quantity > 0 and new_reserved > locked.on_hand:
            raise InsufficientStock(
                "Not enough stock available to reserve.",
                details={
                    "stock_item": locked.pk,
                    "requested": quantity,
                    "available": locked.on_hand - locked.reserved,
                },
            )
    else:
        raise ValueError(f"Unknown affects target: {affects}")

    locked.on_hand = new_on_hand
    locked.reserved = new_reserved
    locked.save(update_fields=["on_hand", "reserved", "updated_at"])

    return StockMovement.objects.create(
        store_id=locked.store_id,
        stock_item=locked,
        movement_type=movement_type,
        quantity=quantity,
        on_hand_after=new_on_hand,
        reserved_after=new_reserved,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        actor=actor,
    )


def receive_stock(stock_item, quantity, *, actor=None, reason=""):
    if quantity <= 0:
        raise StockError("Received quantity must be positive.")
    return record_movement(
        stock_item,
        MovementType.PURCHASE,
        quantity,
        actor=actor,
        reason=reason,
    )


@transaction.atomic
def adjust_stock(stock_item, new_on_hand, *, actor=None, reason=""):
    if new_on_hand < 0:
        raise StockError("Stock level cannot be negative.")
    if not reason:
        raise StockError("A reason is required for manual stock adjustments.")

    current = (
        StockItem.objects.select_for_update()
        .values_list("on_hand", flat=True)
        .get(pk=stock_item.pk)
    )
    delta = new_on_hand - current
    if delta == 0:
        return None
    return record_movement(
        stock_item,
        MovementType.ADJUSTMENT,
        delta,
        actor=actor,
        reason=reason,
    )


def reserve_stock(stock_item, quantity, *, actor=None, order_id=None):
    if quantity <= 0:
        raise StockError("Reserved quantity must be positive.")
    return record_movement(
        stock_item,
        MovementType.ORDER_RESERVE,
        quantity,
        actor=actor,
        affects="reserved",
        reference_type="order",
        reference_id=order_id,
    )


def release_reservation(stock_item, quantity, *, actor=None, order_id=None):
    if quantity <= 0:
        raise StockError("Released quantity must be positive.")
    return record_movement(
        stock_item,
        MovementType.RESERVE_RELEASE,
        -quantity,
        actor=actor,
        affects="reserved",
        reference_type="order",
        reference_id=order_id,
    )


@transaction.atomic
def ship_stock(stock_item, quantity, *, actor=None, order_id=None):
    if quantity <= 0:
        raise StockError("Shipped quantity must be positive.")

    release_reservation(stock_item, quantity, actor=actor, order_id=order_id)
    return record_movement(
        stock_item,
        MovementType.SALE,
        -quantity,
        actor=actor,
        reference_type="order",
        reference_id=order_id,
    )


def restock_return(stock_item, quantity, *, actor=None, return_id=None, reason=""):
    if quantity <= 0:
        raise StockError("Restocked quantity must be positive.")
    return record_movement(
        stock_item,
        MovementType.RETURN_RESTOCK,
        quantity,
        actor=actor,
        reason=reason,
        reference_type="return",
        reference_id=return_id,
    )


def write_off(stock_item, quantity, *, actor=None, reason="", return_id=None):
    if quantity <= 0:
        raise StockError("Written-off quantity must be positive.")
    if not reason:
        raise StockError("A reason is required to write off stock.")
    return record_movement(
        stock_item,
        MovementType.WRITE_OFF,
        -quantity,
        actor=actor,
        reason=reason,
        reference_type="return",
        reference_id=return_id,
    )


def rebuild_stock_from_ledger(stock_item):
    movements = StockMovement.objects.filter(stock_item=stock_item).order_by(
        "created_at", "id"
    )
    on_hand = 0
    reserved = 0
    for movement in movements:
        if movement.movement_type in (
            MovementType.ORDER_RESERVE,
            MovementType.RESERVE_RELEASE,
        ):
            reserved += movement.quantity
        else:
            on_hand += movement.quantity
    return {"on_hand": on_hand, "reserved": reserved}
