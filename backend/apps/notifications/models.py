from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class NotificationType(models.TextChoices):
    NEW_PUBLIC_ORDER = "new_public_order", "New order from the public form"
    LOW_STOCK = "low_stock", "Low stock"
    COD_OVERDUE = "cod_overdue", "COD overdue"
    BOOKING_FAILED = "booking_failed", "Courier booking failed"
    RETURN_RECORDED = "return_recorded", "Return recorded"
    SETTLEMENT_COMMITTED = "settlement_committed", "Settlement committed"
    ORDER_CANCELLED = "order_cancelled", "Order cancelled"


class NotificationLevel(models.TextChoices):
    INFO = "info", "Information"
    WARNING = "warning", "Needs attention"
    CRITICAL = "critical", "Urgent"


class NotificationQuerySet(StoreScopedQuerySet):
    def unread(self):
        return self.filter(is_read=False)

    def for_user(self, user):
        return self.filter(
            models.Q(user__isnull=True) | models.Q(user=user)
        )


class Notification(StoreOwnedModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices
    )
    level = models.CharField(
        max_length=10,
        choices=NotificationLevel.choices,
        default=NotificationLevel.INFO,
    )

    title = models.CharField(max_length=150)
    body = models.CharField(max_length=400, blank=True)

    payload = models.JSONField(default=dict, blank=True)
    link = models.CharField(max_length=200, blank=True)

    dedupe_key = models.CharField(max_length=120, blank=True, db_index=True)

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["store", "is_read", "-created_at"]),
            models.Index(fields=["store", "notification_type"]),
        ]

    def __str__(self):
        return self.title

    def mark_read(self):
        from django.utils import timezone

        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])
        return self
