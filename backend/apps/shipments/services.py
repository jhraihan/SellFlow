import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import APIError
from apps.couriers.adapters.base import CourierError, ParcelDraft
from apps.couriers.adapters.registry import build_adapter
from apps.orders.models import OrderStatus
from apps.orders.services import transition_status

from .models import BookingMode, CodStatus, DeliveryStatusHistory, Shipment

logger = logging.getLogger(__name__)

SYNC_TIERS = (
    (timedelta(days=2), timedelta(minutes=15)),
    (timedelta(days=7), timedelta(hours=2)),
    (timedelta(days=30), timedelta(hours=12)),
)
MAX_SYNC_FAILURES = 10


class ShipmentError(APIError):
    default_code = "SHIPMENT_ERROR"
    default_detail = "Shipment operation failed."


def build_draft(order):
    items = list(order.items.all())
    description = ", ".join(
        f"{i.product_name} x{i.quantity}" for i in items
    )[:255]
    weight = sum(
        (i.product.weight_grams or 0) * i.quantity for i in items
    ) or 500

    return ParcelDraft(
        order_number=order.order_number,
        recipient_name=order.recipient_name,
        recipient_phone=order.recipient_phone,
        address_line=order.shipping_address,
        district=order.shipping_district,
        thana=order.shipping_thana,
        area=order.shipping_area,
        cod_amount=order.cod_amount,
        item_description=description,
        item_quantity=sum(i.quantity for i in items),
        weight_grams=weight,
        special_instruction=order.customer_note[:255],
    )


@transaction.atomic
def book_shipment(
    order,
    store_courier,
    *,
    actor=None,
    manual_consignment_id="",
    advance_order=True,
):
    if store_courier.store_id != order.store_id:
        raise ShipmentError(
            "That courier is not configured for this store.",
            code="COURIER_NOT_IN_STORE",
        )
    if not store_courier.is_enabled:
        raise ShipmentError(
            f"{store_courier.courier.name} is disabled for this store.",
            code="COURIER_DISABLED",
        )

    existing = Shipment.objects.filter(
        order=order, cancelled_at__isnull=True
    ).first()
    if existing is not None:
        raise ShipmentError(
            f"Order {order.order_number} already has an active shipment.",
            code="SHIPMENT_ALREADY_EXISTS",
            details={"shipment_id": existing.id,
                     "consignment_id": existing.consignment_id},
        )

    if order.status not in (
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
        OrderStatus.READY_TO_SHIP,
    ):
        raise ShipmentError(
            "Confirm the order before booking a courier.",
            code="ORDER_NOT_READY",
            details={"status": order.status,
                     "required": ["confirmed", "processing", "ready_to_ship"]},
        )

    adapter = build_adapter(store_courier)
    use_api = store_courier.can_book_via_api and not manual_consignment_id

    if use_api:
        draft = build_draft(order)
        result = adapter.create_parcel(draft)
        mode = BookingMode.API
    else:
        if not manual_consignment_id:
            raise ShipmentError(
                "Enter the consignment id from the courier, or add API "
                "credentials for this courier in settings.",
                code="CONSIGNMENT_ID_REQUIRED",
            )
        from apps.couriers.adapters.base import BookingResult

        result = BookingResult(
            consignment_id=manual_consignment_id.strip(),
            tracking_code=manual_consignment_id.strip(),
        )
        mode = BookingMode.MANUAL

    shipment = Shipment.objects.create(
        store=order.store,
        order=order,
        store_courier=store_courier,
        consignment_id=result.consignment_id,
        tracking_code=result.tracking_code,
        tracking_url=result.tracking_url,
        booking_mode=mode,
        quoted_cost=result.quoted_cost,
        cod_amount=order.cod_amount,
        cod_status=(
            CodStatus.PENDING if order.cod_amount > 0
            else CodStatus.NOT_APPLICABLE
        ),
        raw_booking_request=result.raw_request,
        raw_booking_response=result.raw_response,
        booked_by=actor,
        booked_at=timezone.now(),
    )

    if advance_order and order.status != OrderStatus.SHIPPED:
        if order.status != OrderStatus.READY_TO_SHIP:
            transition_status(
                order, OrderStatus.READY_TO_SHIP, actor=actor,
                note="Auto-advanced for courier booking",
            )
            order.refresh_from_db()
        transition_status(
            order,
            OrderStatus.SHIPPED,
            actor=actor,
            note=f"Booked with {store_courier.courier.name} ({result.consignment_id})",
        )

    return shipment


def due_for_sync(shipment, now=None):
    if not shipment.is_in_transit:
        return False
    if shipment.booking_mode != BookingMode.API:
        return False
    if shipment.sync_failures >= MAX_SYNC_FAILURES:
        return False

    now = now or timezone.now()
    if shipment.last_synced_at is None:
        return True

    age = now - (shipment.booked_at or shipment.created_at)
    interval = timedelta(days=1)
    for max_age, tier_interval in SYNC_TIERS:
        if age <= max_age:
            interval = tier_interval
            break

    return now - shipment.last_synced_at >= interval


@transaction.atomic
def record_tracking_events(shipment, events, *, source="poll", actor=None):
    if not events:
        return shipment

    locked = Shipment.objects.select_for_update().get(pk=shipment.pk)
    applied = []

    for event in events:
        already = DeliveryStatusHistory.objects.filter(
            shipment=locked,
            raw_status=event.raw_status,
            observed_at=event.observed_at,
        ).exists()
        if already:
            continue

        DeliveryStatusHistory.objects.create(
            shipment=locked,
            raw_status=event.raw_status,
            mapped_status=event.mapped_status or "",
            note=event.note or "",
            location=event.location or "",
            source=source,
            raw_payload=event.raw_payload or {},
            observed_at=event.observed_at or timezone.now(),
        )
        applied.append(event)

    if not applied:
        locked.last_synced_at = timezone.now()
        locked.save(update_fields=["last_synced_at", "updated_at"])
        return locked

    latest = applied[-1]
    locked.current_courier_status = latest.raw_status
    locked.last_synced_at = timezone.now()
    locked.sync_failures = 0

    if latest.mapped_status == OrderStatus.DELIVERED:
        locked.delivered_at = latest.observed_at or timezone.now()
        if locked.cod_amount > 0 and locked.cod_status == CodStatus.PENDING:
            locked.cod_status = CodStatus.COLLECTED
            locked.cod_collected_at = locked.delivered_at

    locked.save()

    _apply_to_order(locked, latest, actor=actor)
    return locked


def _apply_to_order(shipment, event, actor=None):
    target = event.mapped_status
    if not target:
        return

    order = shipment.order
    order.refresh_from_db()

    if order.status == target:
        return

    if not order.can_transition_to(target):
        logger.info(
            "Courier reported %s for order %s but that is not a legal move "
            "from %s; recorded in tracking history only.",
            target, order.order_number, order.status,
        )
        return

    try:
        transition_status(
            order,
            target,
            actor=actor,
            note=f"Courier reported: {event.raw_status}",
            reason="other" if target == OrderStatus.CANCELLED else "",
        )
    except APIError as exc:
        logger.warning(
            "Could not apply courier status %s to order %s: %s",
            target, order.order_number, exc,
        )


def sync_shipment(shipment, *, actor=None):
    adapter = build_adapter(shipment.store_courier)

    try:
        events = adapter.track(shipment.consignment_id)
    except NotImplementedError:
        return shipment
    except CourierError as exc:
        Shipment.objects.filter(pk=shipment.pk).update(
            sync_failures=shipment.sync_failures + 1,
            last_synced_at=timezone.now(),
        )
        logger.warning(
            "Tracking sync failed for %s: %s", shipment.consignment_id, exc
        )
        return shipment

    return record_tracking_events(shipment, events, source="poll", actor=actor)


def sync_due_shipments(limit=200, store=None):
    now = timezone.now()
    queryset = Shipment.objects.needs_sync().select_related(
        "store_courier__courier", "order"
    )
    if store is not None:
        queryset = queryset.for_store(store)

    synced = 0
    for shipment in queryset[:limit]:
        if not due_for_sync(shipment, now):
            continue
        sync_shipment(shipment)
        synced += 1
    return synced


@transaction.atomic
def cancel_shipment(shipment, *, actor=None, note=""):
    locked = Shipment.objects.select_for_update().get(pk=shipment.pk)

    if locked.delivered_at is not None:
        raise ShipmentError(
            "A delivered shipment cannot be cancelled.",
            code="SHIPMENT_ALREADY_DELIVERED",
        )
    if locked.cancelled_at is not None:
        raise ShipmentError(
            "This shipment is already cancelled.",
            code="SHIPMENT_ALREADY_CANCELLED",
        )

    adapter = build_adapter(locked.store_courier)
    if locked.booking_mode == BookingMode.API and adapter.supports_cancel:
        try:
            adapter.cancel(locked.consignment_id)
        except (CourierError, NotImplementedError) as exc:
            logger.warning(
                "Courier cancel failed for %s: %s", locked.consignment_id, exc
            )

    locked.cancelled_at = timezone.now()
    locked.cod_status = CodStatus.NOT_APPLICABLE
    locked.save(
        update_fields=["cancelled_at", "cod_status", "updated_at"]
    )
    return locked


def mark_cod_settled(shipment, *, reference="", settled_at=None, actual_cost=None):
    shipment.cod_status = CodStatus.SETTLED
    shipment.cod_settled_at = settled_at or timezone.now()
    shipment.settlement_reference = reference
    if actual_cost is not None:
        shipment.actual_cost = actual_cost
    shipment.save(
        update_fields=[
            "cod_status", "cod_settled_at", "settlement_reference",
            "actual_cost", "updated_at",
        ]
    )
    return shipment
