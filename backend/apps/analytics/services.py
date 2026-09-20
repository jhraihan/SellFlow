from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.catalog.models import StockItem
from apps.customers.models import Customer, RiskLevel
from apps.expenses.models import Expense
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.payments.models import MatchStatus, SettlementLine, SettlementStatus
from apps.returns.models import Return
from apps.shipments.models import CodStatus, Shipment

ZERO = Decimal("0.00")

MONEY = DecimalField(max_digits=16, decimal_places=2)


def _money(expression):
    return Coalesce(expression, Value(ZERO), output_field=MONEY)


def _as_date(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def resolve_period(date_from=None, date_to=None, days=30):
    today = timezone.localdate()
    end = _as_date(date_to, today)
    start = _as_date(date_from, end - timedelta(days=days - 1))
    if start > end:
        start, end = end, start
    return start, end


def profit_report(store, *, date_from=None, date_to=None):
    start, end = resolve_period(date_from, date_to)

    delivered = Order.objects.for_store(store).filter(
        status=OrderStatus.DELIVERED,
        delivered_at__date__gte=start,
        delivered_at__date__lte=end,
    )

    revenue = delivered.aggregate(
        gross_sales=_money(Sum("subtotal")),
        discounts=_money(Sum("discount_amount")),
        delivery_revenue=_money(Sum("delivery_charge")),
        order_count=Count("id"),
    )

    cogs = OrderItem.objects.filter(order__in=delivered).aggregate(
        total=_money(Sum(F("unit_cost") * F("quantity"), output_field=MONEY))
    )["total"]

    shipments = Shipment.objects.for_store(store).filter(
        booked_at__date__gte=start,
        booked_at__date__lte=end,
        cancelled_at__isnull=True,
    )
    delivery_cost = shipments.aggregate(
        total=_money(Sum(Coalesce("actual_cost", "quoted_cost")))
    )["total"]

    returns = Return.objects.for_store(store).filter(
        created_at__date__gte=start, created_at__date__lte=end
    )
    return_totals = returns.aggregate(
        forward=_money(Sum("forward_delivery_cost")),
        charge=_money(Sum("return_charge")),
        written_off=_money(Sum("written_off_value")),
        refunded=_money(Sum("refund_amount")),
        count=Count("id"),
    )
    return_loss = (
        return_totals["forward"]
        + return_totals["charge"]
        + return_totals["written_off"]
    )

    expenses = Expense.objects.for_store(store).filter(
        date__gte=start, date__lte=end
    )
    operating_expenses = expenses.aggregate(
        total=_money(Sum("amount"))
    )["total"]

    gross_sales = revenue["gross_sales"]
    discounts = revenue["discounts"]
    delivery_revenue = revenue["delivery_revenue"]

    net_sales = gross_sales - discounts
    gross_profit = net_sales + delivery_revenue - cogs - delivery_cost
    net_profit = gross_profit - return_loss - operating_expenses

    margin = (
        (net_profit / net_sales * 100).quantize(Decimal("0.01"))
        if net_sales
        else ZERO
    )

    return {
        "period": {"from": start, "to": end},
        "delivered_orders": revenue["order_count"],
        "gross_sales": gross_sales,
        "discounts": discounts,
        "net_sales": net_sales,
        "delivery_revenue": delivery_revenue,
        "cogs": cogs,
        "delivery_cost": delivery_cost,
        "gross_profit": gross_profit,
        "return_loss": return_loss,
        "return_breakdown": {
            "count": return_totals["count"],
            "forward_delivery_cost": return_totals["forward"],
            "return_charge": return_totals["charge"],
            "written_off_value": return_totals["written_off"],
            "refunded": return_totals["refunded"],
        },
        "operating_expenses": operating_expenses,
        "net_profit": net_profit,
        "net_margin_percent": margin,
    }


def _trunc_for(group_by):
    return {
        "day": TruncDay,
        "week": TruncWeek,
        "month": TruncMonth,
    }.get(group_by, TruncDay)


def sales_series(store, *, date_from=None, date_to=None, group_by="day"):
    start, end = resolve_period(date_from, date_to)
    trunc = _trunc_for(group_by)

    delivered = (
        Order.objects.for_store(store)
        .filter(
            status=OrderStatus.DELIVERED,
            delivered_at__date__gte=start,
            delivered_at__date__lte=end,
        )
        .annotate(bucket=trunc("delivered_at"))
        .values("bucket")
        .annotate(
            orders=Count("id"),
            gross_sales=_money(Sum("subtotal")),
            discounts=_money(Sum("discount_amount")),
            delivery_revenue=_money(Sum("delivery_charge")),
        )
        .order_by("bucket")
    )

    placed = (
        Order.objects.for_store(store)
        .filter(created_at__date__gte=start, created_at__date__lte=end)
        .annotate(bucket=trunc("created_at"))
        .values("bucket")
        .annotate(orders=Count("id"), value=_money(Sum("total_amount")))
        .order_by("bucket")
    )
    placed_map = {row["bucket"]: row for row in placed}

    series = []
    for row in delivered:
        bucket = row["bucket"]
        placed_row = placed_map.pop(bucket, None)
        series.append({
            "date": bucket.date() if hasattr(bucket, "date") else bucket,
            "delivered_orders": row["orders"],
            "gross_sales": row["gross_sales"],
            "net_sales": row["gross_sales"] - row["discounts"],
            "delivery_revenue": row["delivery_revenue"],
            "placed_orders": placed_row["orders"] if placed_row else 0,
            "placed_value": placed_row["value"] if placed_row else ZERO,
        })

    for bucket, placed_row in placed_map.items():
        series.append({
            "date": bucket.date() if hasattr(bucket, "date") else bucket,
            "delivered_orders": 0,
            "gross_sales": ZERO,
            "net_sales": ZERO,
            "delivery_revenue": ZERO,
            "placed_orders": placed_row["orders"],
            "placed_value": placed_row["value"],
        })

    series.sort(key=lambda r: r["date"])
    return {"period": {"from": start, "to": end},
            "group_by": group_by, "series": series}


def dashboard(store):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    orders = Order.objects.for_store(store)

    def _day_counts(day):
        placed = orders.filter(created_at__date=day)
        return {
            "orders": placed.count(),
            "value": placed.aggregate(t=_money(Sum("total_amount")))["t"],
            "delivered": orders.filter(
                status=OrderStatus.DELIVERED, delivered_at__date=day
            ).count(),
            "returned": orders.filter(
                status=OrderStatus.RETURNED, returned_at__date=day
            ).count(),
            "cancelled": orders.filter(
                status=OrderStatus.CANCELLED, cancelled_at__date=day
            ).count(),
        }

    today_counts = _day_counts(today)
    yesterday_counts = _day_counts(yesterday)

    today_profit = profit_report(store, date_from=today, date_to=today)

    status_rows = orders.values("status").annotate(n=Count("id"))
    by_status = {row["status"]: row["n"] for row in status_rows}

    pending = by_status.get(OrderStatus.PENDING, 0)
    open_count = sum(
        by_status.get(s, 0)
        for s in (
            OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
            OrderStatus.READY_TO_SHIP, OrderStatus.SHIPPED,
            OrderStatus.OUT_FOR_DELIVERY, OrderStatus.ON_HOLD,
        )
    )

    low_stock = [
        {
            "product_id": item.product_id,
            "product_name": item.product.name,
            "variant": item.variant.label if item.variant else None,
            "available": item.available,
            "threshold": item.product.low_stock_threshold,
        }
        for item in StockItem.objects.for_store(store)
        .select_related("product", "variant")
        .filter(on_hand__lte=F("product__low_stock_threshold"))[:10]
    ]

    settings = getattr(store, "settings", None)
    overdue_days = getattr(settings, "cod_overdue_days", 7)
    cutoff = timezone.now() - timedelta(days=overdue_days)

    cod = Shipment.objects.for_store(store).filter(cancelled_at__isnull=True)
    cod_summary = {
        "in_transit": cod.filter(
            cod_status=CodStatus.PENDING, delivered_at__isnull=True
        ).aggregate(t=_money(Sum("cod_amount")), n=Count("id")),
        "collected": cod.filter(
            cod_status=CodStatus.COLLECTED
        ).aggregate(t=_money(Sum("cod_amount")), n=Count("id")),
        "overdue": cod.filter(
            cod_status__in=[CodStatus.PENDING, CodStatus.COLLECTED],
            delivered_at__lt=cutoff,
        ).aggregate(t=_money(Sum("cod_amount")), n=Count("id")),
    }

    top_products = list(
        OrderItem.objects.filter(
            order__store=store,
            order__status=OrderStatus.DELIVERED,
            order__delivered_at__date__gte=today - timedelta(days=30),
        )
        .values("product_id", "product_name")
        .annotate(
            units=Sum("quantity"),
            revenue=_money(Sum(F("unit_price") * F("quantity"),
                               output_field=MONEY)),
        )
        .order_by("-revenue")[:5]
    )

    risky_customers = Customer.objects.for_store(store).filter(
        risk_level__in=[RiskLevel.HIGH_RISK, RiskLevel.BLACKLISTED]
    ).count()

    def _delta(current, previous):
        if previous == 0:
            return None
        change = (Decimal(current) - Decimal(previous)) / Decimal(previous) * 100
        return change.quantize(Decimal("0.01"))

    return {
        "today": {
            "orders": today_counts["orders"],
            "order_value": today_counts["value"],
            "delivered": today_counts["delivered"],
            "returned": today_counts["returned"],
            "cancelled": today_counts["cancelled"],
            "sales": today_profit["net_sales"],
            "delivery_cost": today_profit["delivery_cost"],
            "net_profit": today_profit["net_profit"],
        },
        "yesterday": {
            "orders": yesterday_counts["orders"],
            "order_value": yesterday_counts["value"],
            "delivered": yesterday_counts["delivered"],
            "returned": yesterday_counts["returned"],
        },
        "change": {
            "orders": _delta(
                today_counts["orders"], yesterday_counts["orders"]
            ),
            "order_value": _delta(
                today_counts["value"], yesterday_counts["value"]
            ),
            "delivered": _delta(
                today_counts["delivered"], yesterday_counts["delivered"]
            ),
        },
        "pending_confirmation": pending,
        "open_orders": open_count,
        "by_status": by_status,
        "low_stock": low_stock,
        "low_stock_count": len(low_stock),
        "cod": {
            key: {"amount": value["t"], "count": value["n"]}
            for key, value in cod_summary.items()
        },
        "top_products": top_products,
        "risky_customers": risky_customers,
    }


def product_performance(store, *, date_from=None, date_to=None, limit=50):
    start, end = resolve_period(date_from, date_to)

    delivered_items = OrderItem.objects.filter(
        order__store=store,
        order__status=OrderStatus.DELIVERED,
        order__delivered_at__date__gte=start,
        order__delivered_at__date__lte=end,
    )

    rows = list(
        delivered_items.values("product_id", "product_name")
        .annotate(
            units=Sum("quantity"),
            revenue=_money(Sum(F("unit_price") * F("quantity"),
                               output_field=MONEY)),
            cost=_money(Sum(F("unit_cost") * F("quantity"),
                            output_field=MONEY)),
            orders=Count("order_id", distinct=True),
        )
        .order_by("-revenue")[:limit]
    )

    from apps.returns.models import ReturnItem

    returned_rows = (
        ReturnItem.objects.filter(
            return_record__store=store,
            return_record__created_at__date__gte=start,
            return_record__created_at__date__lte=end,
        )
        .values("order_item__product_id")
        .annotate(units=Sum("quantity"))
    )
    returned_units = {
        row["order_item__product_id"]: row["units"] for row in returned_rows
    }

    for row in rows:
        margin = row["revenue"] - row["cost"]
        row["margin"] = margin
        row["margin_percent"] = (
            (margin / row["revenue"] * 100).quantize(Decimal("0.01"))
            if row["revenue"]
            else ZERO
        )
        returned = returned_units.get(row["product_id"], 0)
        row["returned_units"] = returned
        total = (row["units"] or 0) + returned
        row["return_rate"] = (
            (Decimal(returned) / Decimal(total) * 100).quantize(Decimal("0.01"))
            if total
            else ZERO
        )

    return {"period": {"from": start, "to": end}, "products": rows}


def courier_performance(store, *, date_from=None, date_to=None):
    start, end = resolve_period(date_from, date_to)

    shipments = Shipment.objects.for_store(store).filter(
        booked_at__date__gte=start,
        booked_at__date__lte=end,
        cancelled_at__isnull=True,
    )

    rows = list(
        shipments.values(
            "store_courier_id", "store_courier__courier__name"
        )
        .annotate(
            shipped=Count("id"),
            delivered=Count("id", filter=Q(delivered_at__isnull=False)),
            cost=_money(Sum(Coalesce("actual_cost", "quoted_cost"))),
            cod_value=_money(Sum("cod_amount")),
        )
        .order_by("-shipped")
    )

    returned_by_courier = {
        row["shipment__store_courier_id"]: row["n"]
        for row in (
            Return.objects.for_store(store)
            .filter(
                created_at__date__gte=start,
                created_at__date__lte=end,
                shipment__isnull=False,
            )
            .values("shipment__store_courier_id")
            .annotate(n=Count("id"))
        )
    }

    for row in rows:
        shipped = row["shipped"] or 0
        delivered = row["delivered"] or 0
        returned = returned_by_courier.get(row["store_courier_id"], 0)

        row["returned"] = returned
        row["success_rate"] = (
            (Decimal(delivered) / Decimal(shipped) * 100).quantize(
                Decimal("0.01")
            )
            if shipped
            else ZERO
        )
        row["return_rate"] = (
            (Decimal(returned) / Decimal(shipped) * 100).quantize(
                Decimal("0.01")
            )
            if shipped
            else ZERO
        )
        row["average_cost"] = (
            (row["cost"] / Decimal(shipped)).quantize(Decimal("0.01"))
            if shipped
            else ZERO
        )

    return {"period": {"from": start, "to": end}, "couriers": rows}


def district_performance(store, *, date_from=None, date_to=None, limit=30):
    start, end = resolve_period(date_from, date_to)

    orders = Order.objects.for_store(store).filter(
        created_at__date__gte=start, created_at__date__lte=end
    )

    rows = list(
        orders.values("shipping_district")
        .annotate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status=OrderStatus.DELIVERED)),
            returned=Count("id", filter=Q(status=OrderStatus.RETURNED)),
            cancelled=Count("id", filter=Q(status=OrderStatus.CANCELLED)),
            revenue=_money(
                Sum("total_amount", filter=Q(status=OrderStatus.DELIVERED))
            ),
        )
        .order_by("-total")[:limit]
    )

    for row in rows:
        shipped = (row["delivered"] or 0) + (row["returned"] or 0)
        row["success_rate"] = (
            (Decimal(row["delivered"]) / Decimal(shipped) * 100).quantize(
                Decimal("0.01")
            )
            if shipped
            else ZERO
        )
        row["return_rate"] = (
            (Decimal(row["returned"]) / Decimal(shipped) * 100).quantize(
                Decimal("0.01")
            )
            if shipped
            else ZERO
        )

    return {"period": {"from": start, "to": end}, "districts": rows}


def staff_performance(store, *, date_from=None, date_to=None):
    start, end = resolve_period(date_from, date_to)

    orders = Order.objects.for_store(store).filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
        created_by__isnull=False,
    )

    rows = list(
        orders.values("created_by_id", "created_by__full_name")
        .annotate(
            created=Count("id"),
            confirmed=Count("id", filter=Q(confirmed_at__isnull=False)),
            delivered=Count("id", filter=Q(status=OrderStatus.DELIVERED)),
            cancelled=Count("id", filter=Q(status=OrderStatus.CANCELLED)),
            value=_money(Sum("total_amount")),
        )
        .order_by("-created")
    )

    for row in rows:
        created = row["created"] or 0
        row["confirmation_rate"] = (
            (Decimal(row["confirmed"]) / Decimal(created) * 100).quantize(
                Decimal("0.01")
            )
            if created
            else ZERO
        )

    return {"period": {"from": start, "to": end}, "staff": rows}


def reconciliation_health(store):
    committed = SettlementLine.objects.filter(
        settlement__store=store,
        settlement__status=SettlementStatus.COMMITTED,
    )

    totals = committed.aggregate(
        lines=Count("id"),
        matched=Count("id", filter=Q(match_status=MatchStatus.MATCHED)),
        mismatched=Count(
            "id", filter=Q(match_status=MatchStatus.AMOUNT_MISMATCH)
        ),
    )

    delivered_with_cod = Shipment.objects.for_store(store).filter(
        delivered_at__isnull=False, cod_amount__gt=0
    )
    settled = delivered_with_cod.filter(cod_status=CodStatus.SETTLED).count()
    total = delivered_with_cod.count()

    coverage = (
        (Decimal(settled) / Decimal(total) * 100).quantize(Decimal("0.01"))
        if total
        else ZERO
    )

    return {
        "delivered_cod_shipments": total,
        "settled_shipments": settled,
        "coverage_percent": coverage,
        "committed_lines": totals["lines"],
        "matched_lines": totals["matched"],
        "mismatched_lines": totals["mismatched"],
    }
