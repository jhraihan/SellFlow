import csv
import io
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.exceptions import APIError
from apps.orders.models import Order, PaymentStatus
from apps.shipments.models import CodStatus, Shipment

from .models import (
    CourierSettlement,
    MatchStatus,
    Payment,
    PaymentDirection,
    PaymentMethod,
    SettlementLine,
    SettlementStatus,
)

CONSIGNMENT_KEYS = (
    "consignment_id", "consignment", "cn_id", "cnid",
    "tracking_code", "tracking_id", "tracking",
    "invoice", "merchant_order_id", "order_id",
)
AMOUNT_KEYS = (
    "collected_amount", "cod_amount", "amount", "collected",
    "cod", "total", "amount_collected",
)
CHARGE_KEYS = (
    "delivery_charge", "charge", "courier_charge", "fee",
    "deducted", "deduction", "service_charge",
)


class PaymentError(APIError):
    default_code = "PAYMENT_ERROR"
    default_detail = "Payment operation failed."


class SettlementError(APIError):
    default_code = "SETTLEMENT_ERROR"
    default_detail = "Settlement operation failed."


def _norm(name):
    return str(name or "").strip().lower().replace(" ", "_").replace("-", "_")


def _pick(row, keys):
    normalised = {_norm(k): v for k, v in row.items()}
    for key in keys:
        value = normalised.get(key)
        if value not in (None, ""):
            return value
    return None


def _to_decimal(value, default=Decimal("0.00")):
    if value in (None, ""):
        return default
    cleaned = str(value).replace(",", "").replace("৳", "").strip()
    cleaned = cleaned.replace("Tk", "").replace("BDT", "").strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return default


@transaction.atomic
def record_payment(
    store,
    *,
    amount,
    method,
    order=None,
    direction=PaymentDirection.IN,
    reference="",
    note="",
    received_at=None,
    actor=None,
):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise PaymentError(
            "A payment amount must be greater than zero.",
            code="INVALID_AMOUNT",
        )

    if order is not None and order.store_id != store.id:
        raise PaymentError("Unknown order.", code="ORDER_NOT_FOUND")

    payment = Payment.objects.create(
        store=store,
        order=order,
        method=method,
        direction=direction,
        amount=amount,
        reference=reference,
        note=note,
        received_at=received_at or timezone.now(),
        recorded_by=actor,
    )

    if order is not None:
        recalculate_order_payment(order)

    return payment


@transaction.atomic
def recalculate_order_payment(order):
    locked = Order.objects.select_for_update().get(pk=order.pk)

    totals = Payment.objects.filter(order=locked).aggregate(
        received=Sum("amount", filter=Q(direction=PaymentDirection.IN)),
        refunded=Sum("amount", filter=Q(direction=PaymentDirection.OUT)),
    )
    received = totals["received"] or Decimal("0.00")
    refunded = totals["refunded"] or Decimal("0.00")
    net = received - refunded

    locked.advance_paid = max(net, Decimal("0.00"))
    locked.cod_amount = max(
        locked.total_amount - locked.advance_paid, Decimal("0.00")
    )

    if refunded > 0 and net <= 0:
        locked.payment_status = PaymentStatus.REFUNDED
    elif net <= 0:
        locked.payment_status = PaymentStatus.UNPAID
    elif net >= locked.total_amount:
        locked.payment_status = PaymentStatus.PAID
    else:
        locked.payment_status = PaymentStatus.PARTIALLY_PAID

    locked.save(
        update_fields=[
            "advance_paid", "cod_amount", "payment_status", "updated_at",
        ]
    )
    return locked


def parse_settlement_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for index, raw in enumerate(reader, start=2):
        consignment = _pick(raw, CONSIGNMENT_KEYS)
        collected = _to_decimal(_pick(raw, AMOUNT_KEYS))
        charge = _to_decimal(_pick(raw, CHARGE_KEYS))

        rows.append({
            "row_number": index,
            "raw_row": {k: str(v) for k, v in raw.items() if k},
            "consignment_id": str(consignment).strip() if consignment else "",
            "collected_amount": collected,
            "deducted_charge": charge,
            "net_amount": collected - charge,
        })
    return rows


@transaction.atomic
def create_settlement_draft(
    store,
    store_courier,
    rows,
    *,
    statement_reference="",
    original_filename="",
    uploaded_file=None,
    actor=None,
):
    if store_courier.store_id != store.id:
        raise SettlementError(
            "That courier is not configured for this store.",
            code="COURIER_NOT_IN_STORE",
        )
    if not rows:
        raise SettlementError(
            "The statement contained no rows.", code="EMPTY_STATEMENT"
        )

    settlement = CourierSettlement.objects.create(
        store=store,
        store_courier=store_courier,
        statement_reference=statement_reference,
        original_filename=original_filename,
        uploaded_file=uploaded_file,
        created_by=actor,
    )

    shipments = {
        s.consignment_id: s
        for s in Shipment.objects.filter(
            store=store,
            store_courier=store_courier,
            consignment_id__in=[r["consignment_id"] for r in rows if r["consignment_id"]],
        ).select_related("order")
    }

    lines = []
    matched = unmatched = mismatch = 0
    total = Decimal("0.00")

    for row in rows:
        shipment = shipments.get(row["consignment_id"])
        expected = shipment.cod_amount if shipment else Decimal("0.00")

        if shipment is None:
            status = MatchStatus.UNMATCHED
            unmatched += 1
            note = "No shipment with this consignment id."
        elif shipment.cod_status == CodStatus.SETTLED:
            status = MatchStatus.ALREADY_SETTLED
            unmatched += 1
            note = "This shipment was already settled."
        elif row["collected_amount"] != expected:
            status = MatchStatus.AMOUNT_MISMATCH
            mismatch += 1
            note = f"Statement says {row['collected_amount']}, order expects {expected}."
        else:
            status = MatchStatus.MATCHED
            matched += 1
            note = ""

        total += row["net_amount"]
        lines.append(
            SettlementLine(
                settlement=settlement,
                row_number=row["row_number"],
                raw_row=row["raw_row"],
                consignment_id=row["consignment_id"],
                collected_amount=row["collected_amount"],
                deducted_charge=row["deducted_charge"],
                net_amount=row["net_amount"],
                shipment=shipment,
                match_status=status,
                expected_amount=expected,
                note=note,
            )
        )

    SettlementLine.objects.bulk_create(lines)

    settlement.total_amount = total
    settlement.matched_count = matched
    settlement.unmatched_count = unmatched
    settlement.mismatch_count = mismatch
    settlement.save(
        update_fields=[
            "total_amount", "matched_count", "unmatched_count",
            "mismatch_count", "updated_at",
        ]
    )
    return settlement


@transaction.atomic
def commit_settlement(settlement, *, actor=None, include_mismatches=False):
    locked = CourierSettlement.objects.select_for_update().get(pk=settlement.pk)

    if locked.status == SettlementStatus.COMMITTED:
        raise SettlementError(
            "This settlement has already been committed.",
            code="SETTLEMENT_ALREADY_COMMITTED",
        )
    if locked.status == SettlementStatus.DISCARDED:
        raise SettlementError(
            "This settlement was discarded.",
            code="SETTLEMENT_DISCARDED",
        )

    allowed = [MatchStatus.MATCHED]
    if include_mismatches:
        allowed.append(MatchStatus.AMOUNT_MISMATCH)

    lines = locked.lines.filter(
        match_status__in=allowed, shipment__isnull=False
    ).select_related("shipment__order")

    if not lines.exists():
        raise SettlementError(
            "No lines in this statement can be settled.",
            code="NOTHING_TO_SETTLE",
            details={
                "matched": locked.matched_count,
                "mismatched": locked.mismatch_count,
                "unmatched": locked.unmatched_count,
            },
        )

    settled_at = timezone.now()
    settled = 0

    for line in lines:
        shipment = line.shipment
        shipment.cod_status = CodStatus.SETTLED
        shipment.cod_settled_at = settled_at
        shipment.settlement_reference = (
            locked.statement_reference or str(locked.pk)
        )
        shipment.actual_cost = line.deducted_charge
        if shipment.cod_collected_at is None:
            shipment.cod_collected_at = settled_at
        shipment.save(
            update_fields=[
                "cod_status", "cod_settled_at", "settlement_reference",
                "actual_cost", "cod_collected_at", "updated_at",
            ]
        )

        record_payment(
            locked.store,
            amount=line.collected_amount,
            method=PaymentMethod.COD,
            order=shipment.order,
            reference=line.consignment_id,
            note=f"COD settled via statement {locked.statement_reference or locked.pk}",
            received_at=settled_at,
            actor=actor,
        )
        settled += 1

    locked.status = SettlementStatus.COMMITTED
    locked.committed_at = settled_at
    locked.save(update_fields=["status", "committed_at", "updated_at"])

    return {"settlement": locked, "settled_count": settled}


def discard_settlement(settlement):
    if settlement.status == SettlementStatus.COMMITTED:
        raise SettlementError(
            "A committed settlement cannot be discarded.",
            code="SETTLEMENT_ALREADY_COMMITTED",
        )
    settlement.status = SettlementStatus.DISCARDED
    settlement.save(update_fields=["status", "updated_at"])
    return settlement


def cod_ledger(store, *, overdue_days=None):
    settings = getattr(store, "settings", None)
    if overdue_days is None:
        overdue_days = getattr(settings, "cod_overdue_days", 7)

    shipments = Shipment.objects.for_store(store).filter(
        cancelled_at__isnull=True
    )

    in_transit = shipments.filter(
        cod_status=CodStatus.PENDING, delivered_at__isnull=True
    ).aggregate(total=Sum("cod_amount"), count=Count("id"))

    collected = shipments.filter(
        cod_status=CodStatus.COLLECTED
    ).aggregate(total=Sum("cod_amount"), count=Count("id"))

    cutoff = timezone.now() - timedelta(days=overdue_days)
    overdue = shipments.filter(
        cod_status__in=[CodStatus.PENDING, CodStatus.COLLECTED],
        delivered_at__lt=cutoff,
    ).aggregate(total=Sum("cod_amount"), count=Count("id"))

    settled = shipments.filter(
        cod_status=CodStatus.SETTLED
    ).aggregate(total=Sum("cod_amount"), count=Count("id"))

    shortfalls = []
    mismatch_lines = (
        SettlementLine.objects.filter(
            settlement__store=store,
            settlement__status=SettlementStatus.COMMITTED,
            match_status=MatchStatus.AMOUNT_MISMATCH,
        )
        .select_related("shipment__order")
        .order_by("-id")[:50]
    )
    for line in mismatch_lines:
        if line.collected_amount < line.expected_amount:
            shortfalls.append({
                "consignment_id": line.consignment_id,
                "order_number": (
                    line.shipment.order.order_number if line.shipment else ""
                ),
                "expected": line.expected_amount,
                "received": line.collected_amount,
                "difference": line.expected_amount - line.collected_amount,
            })

    def _row(bucket):
        return {
            "amount": bucket["total"] or Decimal("0.00"),
            "count": bucket["count"] or 0,
        }

    return {
        "in_transit": _row(in_transit),
        "collected_unsettled": _row(collected),
        "overdue": _row(overdue),
        "settled": _row(settled),
        "overdue_days": overdue_days,
        "shortfalls": shortfalls,
        "shortfall_total": sum(
            (s["difference"] for s in shortfalls), Decimal("0.00")
        ),
    }
