from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.services import restock_return
from apps.core.exceptions import APIError
from apps.orders.models import Order, OrderStatus
from apps.orders.services import resolve_stock_item, transition_status
from apps.payments.models import PaymentDirection, PaymentMethod
from apps.payments.services import record_payment
from apps.shipments.models import CodStatus

from .models import ItemCondition, Return, ReturnItem, ReturnStatus, ReturnType


class ReturnError(APIError):
    default_code = "RETURN_ERROR"
    default_detail = "Return operation failed."


@transaction.atomic
def create_return(
    store,
    order,
    *,
    reason,
    items=None,
    return_type=None,
    shipment=None,
    reason_note="",
    return_charge=Decimal("0.00"),
    actor=None,
    move_order=True,
):
    if order.store_id != store.id:
        raise ReturnError("Unknown order.", code="ORDER_NOT_FOUND")

    if order.status in (OrderStatus.PENDING, OrderStatus.CANCELLED):
        raise ReturnError(
            "Only a shipped or delivered order can be returned.",
            code="ORDER_NOT_RETURNABLE",
            details={"status": order.status},
        )

    existing = Return.objects.filter(order=order).exclude(
        status=ReturnStatus.RESOLVED
    ).first()
    if existing is not None:
        raise ReturnError(
            "This order already has an open return.",
            code="RETURN_ALREADY_OPEN",
            details={"return_id": existing.id},
        )

    order_items = {i.id: i for i in order.items.all()}
    rows = items or [
        {"order_item": item, "quantity": item.quantity}
        for item in order_items.values()
    ]

    normalised = []
    for row in rows:
        item = row["order_item"]
        if not hasattr(item, "id"):
            item = order_items.get(item)
        if item is None or item.id not in order_items:
            raise ReturnError(
                "That item does not belong to this order.",
                code="ITEM_NOT_IN_ORDER",
            )

        quantity = int(row["quantity"])
        if quantity <= 0:
            raise ReturnError(
                "Returned quantity must be positive.",
                code="INVALID_QUANTITY",
            )
        if quantity > item.quantity:
            raise ReturnError(
                f"Cannot return {quantity} of {item.product_name}; the order "
                f"has {item.quantity}.",
                code="QUANTITY_EXCEEDS_ORDER",
                details={"ordered": item.quantity, "requested": quantity},
            )
        normalised.append({
            "order_item": item,
            "quantity": quantity,
            "condition": row.get("condition", ItemCondition.SELLABLE),
            "note": row.get("note", ""),
        })

    if return_type is None:
        total_ordered = sum(i.quantity for i in order_items.values())
        total_returned = sum(r["quantity"] for r in normalised)
        return_type = (
            ReturnType.FULL if total_returned >= total_ordered
            else ReturnType.PARTIAL
        )

    if shipment is None:
        shipment = order.shipments.filter(cancelled_at__isnull=True).first()

    forward_cost = Decimal("0.00")
    if shipment is not None:
        forward_cost = shipment.actual_cost or shipment.quoted_cost
    if not forward_cost:
        forward_cost = order.delivery_charge

    record = Return.objects.create(
        store=store,
        order=order,
        shipment=shipment,
        return_type=return_type,
        reason=reason,
        reason_note=reason_note,
        forward_delivery_cost=forward_cost,
        return_charge=Decimal(str(return_charge)),
        created_by=actor,
    )

    ReturnItem.objects.bulk_create([
        ReturnItem(
            return_record=record,
            order_item=row["order_item"],
            quantity=row["quantity"],
            condition=row["condition"],
            note=row["note"],
        )
        for row in normalised
    ])

    if shipment is not None and shipment.cod_status != CodStatus.SETTLED:
        shipment.cod_status = CodStatus.NOT_APPLICABLE
        shipment.save(update_fields=["cod_status", "updated_at"])

    if move_order and order.status != OrderStatus.RETURNED:
        if order.can_transition_to(OrderStatus.RETURNED):
            transition_status(
                order,
                OrderStatus.RETURNED,
                actor=actor,
                note=f"Return opened: {record.get_reason_display()}",
            )

    return record


@transaction.atomic
def receive_return(record, *, actor=None):
    locked = Return.objects.select_for_update().get(pk=record.pk)

    if locked.status != ReturnStatus.INITIATED:
        raise ReturnError(
            "Only an initiated return can be marked received.",
            code="RETURN_NOT_INITIATED",
            details={"status": locked.status},
        )

    locked.status = ReturnStatus.RECEIVED
    locked.received_at = timezone.now()
    locked.save(update_fields=["status", "received_at", "updated_at"])
    return locked


@transaction.atomic
def resolve_return(
    record,
    *,
    item_dispositions=None,
    refund_amount=None,
    refund_method=PaymentMethod.BKASH,
    resolution_note="",
    actor=None,
):
    locked = Return.objects.select_for_update().get(pk=record.pk)

    if locked.status == ReturnStatus.RESOLVED:
        raise ReturnError(
            "This return is already resolved.",
            code="RETURN_ALREADY_RESOLVED",
        )

    dispositions = {}
    for row in item_dispositions or []:
        dispositions[int(row["return_item"])] = row

    written_off = Decimal("0.00")

    for item in locked.items.select_related(
        "order_item__product", "order_item__variant"
    ):
        row = dispositions.get(item.id, {})
        condition = row.get("condition", item.condition)
        should_restock = row.get(
            "restock", condition == ItemCondition.SELLABLE
        )

        stock_item = resolve_stock_item(
            item.order_item.product, item.order_item.variant
        )

        if should_restock and condition == ItemCondition.SELLABLE:
            restock_return(
                stock_item,
                item.quantity,
                actor=actor,
                return_id=locked.pk,
                reason=f"Return {locked.pk} restocked",
            )
            item.restocked = True
        else:
            written_off += item.cost_value
            item.restocked = False

        item.condition = condition
        item.save(update_fields=["condition", "restocked"])

    if refund_amount is None:
        refund_amount = Decimal("0.00")
    refund_amount = Decimal(str(refund_amount))

    if refund_amount > 0:
        already_paid = locked.order.advance_paid
        if refund_amount > already_paid:
            raise ReturnError(
                "The refund cannot exceed what the customer actually paid.",
                code="REFUND_EXCEEDS_PAID",
                details={
                    "paid": str(already_paid),
                    "requested": str(refund_amount),
                },
            )
        record_payment(
            locked.store,
            amount=refund_amount,
            method=refund_method,
            order=locked.order,
            direction=PaymentDirection.OUT,
            note=f"Refund for return {locked.pk}",
            actor=actor,
        )

    locked.written_off_value = written_off
    locked.refund_amount = refund_amount
    locked.resolution_note = resolution_note
    locked.status = ReturnStatus.RESOLVED
    locked.resolved_at = timezone.now()
    locked.save()

    return locked


def return_analytics(store, *, date_from=None, date_to=None):
    from django.db.models import Count, Sum

    queryset = Return.objects.for_store(store)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    by_reason = list(
        queryset.values("reason")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    by_district = list(
        queryset.values("order__shipping_district")
        .annotate(count=Count("id"))
        .order_by("-count")[:20]
    )

    by_courier = list(
        queryset.filter(shipment__isnull=False)
        .values("shipment__store_courier__courier__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    by_product = list(
        ReturnItem.objects.filter(return_record__in=queryset)
        .values("order_item__product_name")
        .annotate(
            quantity=Sum("quantity"), returns=Count("return_record", distinct=True)
        )
        .order_by("-quantity")[:20]
    )

    totals = queryset.aggregate(
        total_returns=Count("id"),
        forward_cost=Sum("forward_delivery_cost"),
        return_charge=Sum("return_charge"),
        written_off=Sum("written_off_value"),
        refunded=Sum("refund_amount"),
    )

    shipped = Order.objects.for_store(store).filter(
        status__in=[
            OrderStatus.SHIPPED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.RETURNED,
        ]
    )
    if date_from:
        shipped = shipped.filter(created_at__date__gte=date_from)
    if date_to:
        shipped = shipped.filter(created_at__date__lte=date_to)
    shipped_count = shipped.count()

    total_returns = totals["total_returns"] or 0
    rate = (
        (Decimal(total_returns) / Decimal(shipped_count) * 100).quantize(
            Decimal("0.01")
        )
        if shipped_count
        else Decimal("0.00")
    )

    loss = (
        (totals["forward_cost"] or Decimal("0.00"))
        + (totals["return_charge"] or Decimal("0.00"))
        + (totals["written_off"] or Decimal("0.00"))
    )

    return {
        "total_returns": total_returns,
        "shipped_orders": shipped_count,
        "return_rate": rate,
        "total_loss": loss,
        "forward_delivery_cost": totals["forward_cost"] or Decimal("0.00"),
        "return_charge": totals["return_charge"] or Decimal("0.00"),
        "written_off_value": totals["written_off"] or Decimal("0.00"),
        "refunded": totals["refunded"] or Decimal("0.00"),
        "by_reason": by_reason,
        "by_district": by_district,
        "by_courier": by_courier,
        "by_product": by_product,
    }
