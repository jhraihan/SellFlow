from decimal import Decimal

from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class ReturnType(models.TextChoices):
    FULL = "full", "Full return"
    PARTIAL = "partial", "Partial return"
    EXCHANGE = "exchange", "Exchange"


class ReturnReason(models.TextChoices):
    CUSTOMER_REFUSED = "customer_refused", "Customer refused delivery"
    WRONG_ITEM = "wrong_item", "Wrong item sent"
    DAMAGED = "damaged", "Damaged in transit"
    SIZE_ISSUE = "size_issue", "Size or fit issue"
    NOT_AVAILABLE = "not_available", "Customer not available"
    QUALITY = "quality", "Quality not as expected"
    FAKE_ORDER = "fake_order", "Fake order"
    OTHER = "other", "Other"


class ReturnStatus(models.TextChoices):
    INITIATED = "initiated", "Initiated"
    RECEIVED = "received", "Received back"
    RESOLVED = "resolved", "Resolved"


class ItemCondition(models.TextChoices):
    SELLABLE = "sellable", "Sellable"
    DAMAGED = "damaged", "Damaged"


class ReturnQuerySet(StoreScopedQuerySet):
    def unresolved(self):
        return self.exclude(status=ReturnStatus.RESOLVED)


class Return(StoreOwnedModel):
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="returns"
    )
    shipment = models.ForeignKey(
        "shipments.Shipment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="returns",
    )

    return_type = models.CharField(
        max_length=20, choices=ReturnType.choices, default=ReturnType.FULL
    )
    reason = models.CharField(max_length=30, choices=ReturnReason.choices)
    reason_note = models.CharField(max_length=300, blank=True)

    status = models.CharField(
        max_length=20,
        choices=ReturnStatus.choices,
        default=ReturnStatus.INITIATED,
    )

    forward_delivery_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    return_charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    written_off_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    refund_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    resolution_note = models.CharField(max_length=300, blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_returns",
    )
    received_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = ReturnQuerySet.as_manager()

    class Meta:
        db_table = "returns_return"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "status"]),
            models.Index(fields=["store", "reason"]),
        ]

    def __str__(self):
        return f"Return for {self.order.order_number}"

    @property
    def total_loss(self):
        return (
            self.forward_delivery_cost
            + self.return_charge
            + self.written_off_value
        )

    @property
    def is_resolved(self):
        return self.status == ReturnStatus.RESOLVED


class ReturnItem(models.Model):
    return_record = models.ForeignKey(
        Return, on_delete=models.CASCADE, related_name="items"
    )
    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.PROTECT, related_name="returns"
    )

    quantity = models.PositiveIntegerField()
    condition = models.CharField(
        max_length=20,
        choices=ItemCondition.choices,
        default=ItemCondition.SELLABLE,
    )
    restocked = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "returns_return_item"
        ordering = ["id"]

    def __str__(self):
        return f"{self.order_item.product_name} x{self.quantity}"

    @property
    def value(self):
        return self.order_item.unit_price * self.quantity

    @property
    def cost_value(self):
        return self.order_item.unit_cost * self.quantity
