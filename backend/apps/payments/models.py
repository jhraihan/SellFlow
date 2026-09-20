from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on Delivery"
    BKASH = "bkash", "bKash"
    NAGAD = "nagad", "Nagad"
    ROCKET = "rocket", "Rocket"
    BANK = "bank", "Bank transfer"
    CASH = "cash", "Cash in hand"
    OTHER = "other", "Other"


class PaymentDirection(models.TextChoices):
    IN = "in", "Received"
    OUT = "out", "Paid out"


class PaymentQuerySet(StoreScopedQuerySet):
    def inbound(self):
        return self.filter(direction=PaymentDirection.IN)

    def outbound(self):
        return self.filter(direction=PaymentDirection.OUT)


class Payment(StoreOwnedModel):
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )

    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    direction = models.CharField(
        max_length=5,
        choices=PaymentDirection.choices,
        default=PaymentDirection.IN,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=300, blank=True)

    received_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    is_verified = models.BooleanField(default=False)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        db_table = "payments_payment"
        ordering = ["-received_at", "-id"]
        indexes = [
            models.Index(fields=["store", "-received_at"]),
            models.Index(fields=["store", "method"]),
            models.Index(fields=["order"]),
        ]

    def __str__(self):
        sign = "+" if self.direction == PaymentDirection.IN else "-"
        return f"{sign}{self.amount} via {self.method}"

    @property
    def signed_amount(self):
        if self.direction == PaymentDirection.OUT:
            return -self.amount
        return self.amount


class SettlementStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMMITTED = "committed", "Committed"
    DISCARDED = "discarded", "Discarded"


class MatchStatus(models.TextChoices):
    MATCHED = "matched", "Matched"
    UNMATCHED = "unmatched", "No shipment found"
    AMOUNT_MISMATCH = "amount_mismatch", "Amount differs"
    ALREADY_SETTLED = "already_settled", "Already settled"


class CourierSettlement(StoreOwnedModel):
    store_courier = models.ForeignKey(
        "couriers.StoreCourier",
        on_delete=models.PROTECT,
        related_name="settlements",
    )

    statement_reference = models.CharField(max_length=120, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    uploaded_file = models.FileField(
        upload_to="settlements/", null=True, blank=True
    )
    original_filename = models.CharField(max_length=255, blank=True)

    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    matched_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    mismatch_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.DRAFT,
    )

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_settlements",
    )
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_courier_settlement"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "status"])]

    def __str__(self):
        return f"Settlement {self.statement_reference or self.pk}"

    @property
    def is_committed(self):
        return self.status == SettlementStatus.COMMITTED

    @property
    def line_count(self):
        return self.lines.count()


class SettlementLine(models.Model):
    settlement = models.ForeignKey(
        CourierSettlement, on_delete=models.CASCADE, related_name="lines"
    )

    row_number = models.PositiveIntegerField(default=0)
    raw_row = models.JSONField(default=dict, blank=True)

    consignment_id = models.CharField(max_length=100, blank=True)
    collected_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deducted_charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    shipment = models.ForeignKey(
        "shipments.Shipment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlement_lines",
    )
    match_status = models.CharField(
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.UNMATCHED,
    )
    expected_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "payments_settlement_line"
        ordering = ["row_number", "id"]
        indexes = [
            models.Index(fields=["settlement", "match_status"]),
            models.Index(fields=["consignment_id"]),
        ]

    def __str__(self):
        return f"{self.consignment_id}: {self.net_amount}"

    @property
    def difference(self):
        return self.collected_amount - self.expected_amount
