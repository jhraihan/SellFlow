from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Plan(TimeStampedModel):
    name = models.CharField(max_length=60)
    code = models.SlugField(max_length=40, unique=True)

    monthly_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    order_limit = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Orders per billing period. Blank means unlimited.",
    )
    staff_limit = models.PositiveSmallIntegerField(default=1)
    courier_limit = models.PositiveSmallIntegerField(default=1)
    sms_credits = models.PositiveIntegerField(default=0)

    allows_api_courier = models.BooleanField(default=False)
    allows_analytics = models.BooleanField(default=True)

    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "billing_plan"
        ordering = ["sort_order", "monthly_price"]

    def __str__(self):
        return self.name

    @property
    def is_unlimited(self):
        return self.order_limit is None


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELLED = "cancelled", "Cancelled"


class Subscription(TimeStampedModel):
    store = models.OneToOneField(
        "stores.Store", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )

    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )

    period_start = models.DateField(default=timezone.localdate)
    period_end = models.DateField(null=True, blank=True)

    orders_used = models.PositiveIntegerField(default=0)

    activated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activated_subscriptions",
    )
    payment_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "billing_subscription"

    def __str__(self):
        return f"{self.store} on {self.plan}"

    @property
    def is_active(self):
        return self.status == SubscriptionStatus.ACTIVE

    @property
    def order_limit(self):
        return self.plan.order_limit

    @property
    def orders_remaining(self):
        if self.plan.is_unlimited:
            return None
        return max(self.plan.order_limit - self.orders_used, 0)

    @property
    def usage_percent(self):
        if self.plan.is_unlimited or not self.plan.order_limit:
            return Decimal("0.00")
        percent = Decimal(self.orders_used) / Decimal(self.plan.order_limit) * 100
        return percent.quantize(Decimal("0.01"))

    @property
    def is_near_limit(self):
        return not self.plan.is_unlimited and self.usage_percent >= 80

    @property
    def is_over_limit(self):
        if self.plan.is_unlimited:
            return False
        return self.orders_used >= self.plan.order_limit

    def period_expired(self, today=None):
        if self.period_end is None:
            return False
        return (today or timezone.localdate()) > self.period_end
