from decimal import Decimal

from django.db import models

from apps.accounts.models import normalise_bd_phone
from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class RiskLevel(models.TextChoices):
    GOOD = "good", "Good"
    WATCH = "watch", "Watch"
    HIGH_RISK = "high_risk", "High Risk"
    BLACKLISTED = "blacklisted", "Blacklisted"


class CustomerQuerySet(StoreScopedQuerySet):
    def risky(self):
        return self.filter(
            risk_level__in=[RiskLevel.HIGH_RISK, RiskLevel.BLACKLISTED]
        )

    def by_phone(self, phone):
        try:
            normalised = normalise_bd_phone(phone)
        except Exception:
            return self.none()
        return self.filter(phone=normalised)


class Customer(StoreOwnedModel):
    phone = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=150)
    alt_phone = models.CharField(max_length=20, blank=True)

    facebook_url = models.URLField(blank=True)
    facebook_name = models.CharField(max_length=150, blank=True)

    notes = models.TextField(blank=True)

    risk_level = models.CharField(
        max_length=20, choices=RiskLevel.choices, default=RiskLevel.GOOD
    )
    is_blacklisted = models.BooleanField(default=False)
    blacklist_reason = models.CharField(max_length=200, blank=True)

    total_orders = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    returned_count = models.PositiveIntegerField(default=0)
    cancelled_count = models.PositiveIntegerField(default=0)
    lifetime_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    last_order_at = models.DateTimeField(null=True, blank=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        db_table = "customers_customer"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "phone"], name="uniq_store_customer_phone"
            )
        ]
        indexes = [
            models.Index(fields=["store", "risk_level"]),
            models.Index(fields=["store", "-last_order_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = normalise_bd_phone(self.phone)
        if self.alt_phone:
            self.alt_phone = normalise_bd_phone(self.alt_phone)
        if self.is_blacklisted:
            self.risk_level = RiskLevel.BLACKLISTED
        super().save(*args, **kwargs)

    @property
    def shipped_count(self):
        return self.delivered_count + self.returned_count

    @property
    def return_rate(self):
        if self.shipped_count == 0:
            return Decimal("0.00")
        rate = Decimal(self.returned_count) / Decimal(self.shipped_count) * 100
        return rate.quantize(Decimal("0.01"))

    @property
    def success_rate(self):
        if self.shipped_count == 0:
            return Decimal("0.00")
        rate = Decimal(self.delivered_count) / Decimal(self.shipped_count) * 100
        return rate.quantize(Decimal("0.01"))

    def compute_risk_level(self, settings=None):
        if self.is_blacklisted:
            return RiskLevel.BLACKLISTED

        if settings is None:
            settings = getattr(self.store, "settings", None)

        count_threshold = getattr(settings, "fraud_return_count_threshold", 3)
        rate_threshold = Decimal(
            str(getattr(settings, "fraud_return_rate_threshold", 40))
        )

        if self.shipped_count == 0:
            return RiskLevel.GOOD

        rate = self.return_rate
        if self.returned_count >= count_threshold or rate >= rate_threshold:
            return RiskLevel.HIGH_RISK
        if self.returned_count > 0 or rate >= (rate_threshold / 2):
            return RiskLevel.WATCH
        return RiskLevel.GOOD

    def refresh_risk_level(self, settings=None, commit=True):
        level = self.compute_risk_level(settings)
        if level != self.risk_level:
            self.risk_level = level
            if commit:
                self.save(update_fields=["risk_level", "updated_at"])
        return level


class CustomerAddress(StoreOwnedModel):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=40, blank=True)

    division = models.CharField(max_length=60, blank=True)
    district = models.CharField(max_length=60)
    thana = models.CharField(max_length=60, blank=True)
    area = models.CharField(max_length=100, blank=True)
    address_line = models.CharField(max_length=255)

    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "customers_address"
        ordering = ["-is_default", "-created_at"]
        indexes = [models.Index(fields=["customer", "is_default"])]

    def __str__(self):
        return f"{self.address_line}, {self.district}"

    def save(self, *args, **kwargs):
        if not self.store_id and self.customer_id:
            self.store_id = self.customer.store_id
        super().save(*args, **kwargs)
        if self.is_default:
            CustomerAddress.objects.filter(customer=self.customer).exclude(
                pk=self.pk
            ).update(is_default=False)

    @property
    def full_address(self):
        parts = [self.address_line, self.area, self.thana, self.district]
        return ", ".join(p for p in parts if p)
