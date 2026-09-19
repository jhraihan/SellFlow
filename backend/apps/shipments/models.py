from decimal import Decimal

from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class BookingMode(models.TextChoices):
    API = "api", "Booked via courier API"
    MANUAL = "manual", "Entered manually"


class CodStatus(models.TextChoices):
    NOT_APPLICABLE = "not_applicable", "Not applicable"
    PENDING = "pending", "Pending collection"
    COLLECTED = "collected", "Collected by courier"
    SETTLED = "settled", "Settled to seller"


class ShipmentQuerySet(StoreScopedQuerySet):
    def in_transit(self):
        return self.filter(
            delivered_at__isnull=True,
            cancelled_at__isnull=True,
        )

    def needs_sync(self):
        return self.in_transit().filter(booking_mode=BookingMode.API)

    def cod_outstanding(self):
        return self.filter(
            cod_status__in=[CodStatus.PENDING, CodStatus.COLLECTED]
        )


class Shipment(StoreOwnedModel):
    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="shipments"
    )
    store_courier = models.ForeignKey(
        "couriers.StoreCourier",
        on_delete=models.PROTECT,
        related_name="shipments",
    )

    consignment_id = models.CharField(max_length=100, db_index=True)
    tracking_code = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)

    booking_mode = models.CharField(
        max_length=10, choices=BookingMode.choices, default=BookingMode.MANUAL
    )

    quoted_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    actual_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    cod_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    cod_status = models.CharField(
        max_length=20, choices=CodStatus.choices, default=CodStatus.PENDING
    )
    cod_collected_at = models.DateTimeField(null=True, blank=True)
    cod_settled_at = models.DateTimeField(null=True, blank=True)
    settlement_reference = models.CharField(max_length=120, blank=True)

    current_courier_status = models.CharField(max_length=80, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_failures = models.PositiveSmallIntegerField(default=0)

    raw_booking_request = models.JSONField(default=dict, blank=True)
    raw_booking_response = models.JSONField(default=dict, blank=True)

    booked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booked_shipments",
    )

    booked_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    objects = ShipmentQuerySet.as_manager()

    class Meta:
        db_table = "shipments_shipment"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store_courier", "consignment_id"],
                name="uniq_courier_consignment",
            )
        ]
        indexes = [
            models.Index(fields=["store", "cod_status"]),
            models.Index(fields=["store", "-created_at"]),
            models.Index(fields=["consignment_id"]),
        ]

    def __str__(self):
        return f"{self.consignment_id} ({self.order.order_number})"

    @property
    def courier_name(self):
        return self.store_courier.courier.name

    @property
    def is_in_transit(self):
        return self.delivered_at is None and self.cancelled_at is None

    @property
    def cod_is_outstanding(self):
        return self.cod_status in (CodStatus.PENDING, CodStatus.COLLECTED)


class DeliveryStatusHistory(models.Model):
    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name="tracking_history"
    )

    raw_status = models.CharField(max_length=80)
    mapped_status = models.CharField(max_length=30, blank=True)
    note = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=150, blank=True)

    source = models.CharField(max_length=20, default="poll")
    raw_payload = models.JSONField(default=dict, blank=True)

    observed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shipments_delivery_status_history"
        ordering = ["-observed_at", "-id"]
        indexes = [models.Index(fields=["shipment", "-observed_at"])]

    def __str__(self):
        return f"{self.shipment_id}: {self.raw_status}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Delivery status history rows are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Delivery status history rows cannot be deleted.")
