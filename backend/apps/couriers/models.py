from django.db import models

from apps.core.encryption import EncryptedJSONField
from apps.core.models import StoreOwnedModel, TimeStampedModel


class Courier(TimeStampedModel):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)
    adapter_key = models.CharField(max_length=40)
    logo = models.ImageField(upload_to="couriers/", blank=True, null=True)

    supports_api = models.BooleanField(default=False)
    supports_webhook = models.BooleanField(default=False)
    supports_quote = models.BooleanField(default=False)
    supports_cancel = models.BooleanField(default=False)

    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "couriers_courier"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StoreCourier(StoreOwnedModel):
    courier = models.ForeignKey(
        Courier, on_delete=models.PROTECT, related_name="store_links"
    )

    credentials = EncryptedJSONField(blank=True, default=dict)
    config = models.JSONField(blank=True, default=dict)

    is_enabled = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "couriers_store_courier"
        ordering = ["-is_default", "courier__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "courier"], name="uniq_store_courier"
            )
        ]

    def __str__(self):
        return f"{self.courier.name} for {self.store.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            StoreCourier.objects.filter(store_id=self.store_id).exclude(
                pk=self.pk
            ).update(is_default=False)

    @property
    def has_credentials(self):
        return bool(self.credentials)

    @property
    def can_book_via_api(self):
        return (
            self.is_enabled
            and self.courier.supports_api
            and self.has_credentials
        )
