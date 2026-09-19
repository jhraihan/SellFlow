from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PROCESSING = "processing", "Processing"
    READY_TO_SHIP = "ready_to_ship", "Ready to Ship"
    SHIPPED = "shipped", "Shipped"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    RETURNED = "returned", "Returned"
    ON_HOLD = "on_hold", "On Hold"


LEGAL_TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.CONFIRMED,
        OrderStatus.CANCELLED,
        OrderStatus.ON_HOLD,
    },
    OrderStatus.CONFIRMED: {
        OrderStatus.PROCESSING,
        OrderStatus.READY_TO_SHIP,
        OrderStatus.CANCELLED,
        OrderStatus.ON_HOLD,
    },
    OrderStatus.PROCESSING: {
        OrderStatus.READY_TO_SHIP,
        OrderStatus.CANCELLED,
        OrderStatus.ON_HOLD,
    },
    OrderStatus.READY_TO_SHIP: {
        OrderStatus.SHIPPED,
        OrderStatus.CANCELLED,
        OrderStatus.ON_HOLD,
    },
    OrderStatus.SHIPPED: {
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
        OrderStatus.RETURNED,
    },
    OrderStatus.OUT_FOR_DELIVERY: {
        OrderStatus.DELIVERED,
        OrderStatus.RETURNED,
        OrderStatus.SHIPPED,
    },
    OrderStatus.DELIVERED: {
        OrderStatus.RETURNED,
    },
    OrderStatus.ON_HOLD: {
        OrderStatus.PENDING,
        OrderStatus.CONFIRMED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CANCELLED: set(),
    OrderStatus.RETURNED: set(),
}

STOCK_RESERVED_FROM = {
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
    OrderStatus.READY_TO_SHIP,
}

EDITABLE_STATUSES = {OrderStatus.PENDING, OrderStatus.CONFIRMED}

OPEN_STATUSES = {
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
    OrderStatus.READY_TO_SHIP,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.ON_HOLD,
}


class OrderSource(models.TextChoices):
    MESSENGER = "messenger", "Facebook Messenger"
    INSTAGRAM = "instagram", "Instagram"
    WHATSAPP = "whatsapp", "WhatsApp"
    PHONE = "phone", "Phone call"
    COMMENT = "comment", "Facebook comment"
    PUBLIC_FORM = "public_form", "Public order form"
    MANUAL = "manual", "Manual entry"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"


class CancelReason(models.TextChoices):
    CUSTOMER_CANCELLED = "customer_cancelled", "Customer cancelled"
    FAKE_ORDER = "fake_order", "Fake or prank order"
    UNREACHABLE = "unreachable", "Customer unreachable"
    OUT_OF_STOCK = "out_of_stock", "Out of stock"
    DUPLICATE = "duplicate", "Duplicate order"
    PRICE_DISPUTE = "price_dispute", "Price disagreement"
    OTHER = "other", "Other"


class CallOutcome(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    NO_ANSWER = "no_answer", "No answer"
    CALL_LATER = "call_later", "Asked to call later"
    CANCELLED = "cancelled", "Cancelled"
    FAKE = "fake", "Fake order"


class OrderQuerySet(StoreScopedQuerySet):
    def open(self):
        return self.filter(status__in=OPEN_STATUSES)

    def needs_confirmation(self):
        return self.filter(status=OrderStatus.PENDING)

    def delivered(self):
        return self.filter(status=OrderStatus.DELIVERED)


class Order(StoreOwnedModel):
    order_number = models.CharField(max_length=32, db_index=True)

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="orders",
    )

    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=20)
    shipping_district = models.CharField(max_length=60)
    shipping_thana = models.CharField(max_length=60, blank=True)
    shipping_area = models.CharField(max_length=100, blank=True)
    shipping_address = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    source = models.CharField(
        max_length=20, choices=OrderSource.choices, default=OrderSource.MANUAL
    )

    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    advance_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    cod_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )

    internal_note = models.TextField(blank=True)
    customer_note = models.TextField(blank=True)

    confirmation_attempts = models.PositiveSmallIntegerField(default=0)
    last_call_outcome = models.CharField(
        max_length=20, choices=CallOutcome.choices, blank=True
    )
    last_call_at = models.DateTimeField(null=True, blank=True)

    cancel_reason = models.CharField(
        max_length=30, choices=CancelReason.choices, blank=True
    )
    cancel_note = models.CharField(max_length=200, blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
    )

    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        db_table = "orders_order"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "order_number"], name="uniq_store_order_number"
            )
        ]
        indexes = [
            models.Index(fields=["store", "status", "-created_at"]),
            models.Index(fields=["store", "-created_at"]),
            models.Index(fields=["store", "customer"]),
        ]

    def __str__(self):
        return self.order_number

    @property
    def is_editable(self):
        return self.status in EDITABLE_STATUSES

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def has_reserved_stock(self):
        return self.status in STOCK_RESERVED_FROM

    @property
    def amount_due(self):
        return self.total_amount - self.advance_paid

    def can_transition_to(self, target):
        return target in LEGAL_TRANSITIONS.get(self.status, set())

    def allowed_transitions(self):
        return sorted(LEGAL_TRANSITIONS.get(self.status, set()))

    def recalculate_totals(self, commit=False):
        items = self.items.all()
        self.subtotal = sum(
            (item.line_total for item in items), Decimal("0.00")
        )
        self.total_amount = (
            self.subtotal - self.discount_amount + self.delivery_charge
        )
        self.cod_amount = max(
            self.total_amount - self.advance_paid, Decimal("0.00")
        )

        if self.advance_paid <= 0:
            self.payment_status = PaymentStatus.UNPAID
        elif self.advance_paid >= self.total_amount:
            self.payment_status = PaymentStatus.PAID
        else:
            self.payment_status = PaymentStatus.PARTIALLY_PAID

        if commit:
            self.save(
                update_fields=[
                    "subtotal",
                    "total_amount",
                    "cod_amount",
                    "payment_status",
                    "updated_at",
                ]
            )
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="order_items"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )

    product_name = models.CharField(max_length=200)
    variant_label = models.CharField(max_length=120, blank=True)
    sku = models.CharField(max_length=64, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders_order_item"
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    @property
    def line_cost(self):
        return self.unit_cost * self.quantity

    @property
    def line_margin(self):
        return self.line_total - self.line_cost


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        max_length=20, choices=OrderStatus.choices, blank=True
    )
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    note = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders_status_history"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["order", "created_at"])]

    def __str__(self):
        return f"{self.order_id}: {self.from_status} -> {self.to_status}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Status history rows are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Status history rows cannot be deleted.")
