from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import SoftDeleteManager, SoftDeleteModel, TimeStampedModel


class StoreRole(models.TextChoices):

    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    ORDER_STAFF = "order_staff", "Order Staff"
    DELIVERY_STAFF = "delivery_staff", "Delivery Staff"
    ACCOUNTANT = "accountant", "Accountant"


ROLE_RANK = {
    StoreRole.OWNER: 0,
    StoreRole.MANAGER: 1,
    StoreRole.ACCOUNTANT: 2,
    StoreRole.ORDER_STAFF: 3,
    StoreRole.DELIVERY_STAFF: 4,
}


class BusinessType(models.TextChoices):
    FASHION = "fashion", "Fashion & Clothing"
    ELECTRONICS = "electronics", "Electronics & Gadgets"
    BEAUTY = "beauty", "Beauty & Cosmetics"
    FOOD = "food", "Food & Grocery"
    HOME = "home", "Home & Living"
    BABY = "baby", "Baby & Kids"
    OTHER = "other", "Other"


class Store(SoftDeleteModel, TimeStampedModel):

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, db_index=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_stores",
    )

    logo = models.ImageField(upload_to="store_logos/", blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)

    business_type = models.CharField(
        max_length=20, choices=BusinessType.choices, default=BusinessType.OTHER
    )

    address_line = models.CharField(max_length=255, blank=True)
    district = models.CharField(max_length=60, blank=True)

    facebook_page_url = models.URLField(blank=True)
    instagram_handle = models.CharField(max_length=60, blank=True)

    order_prefix = models.CharField(max_length=8, default="ORD")
    order_sequence = models.PositiveIntegerField(default=1000)

    is_active = models.BooleanField(default=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "stores_store"
        ordering = ["-created_at"]
        base_manager_name = "objects"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    def _generate_slug(self):
        base = slugify(self.name) or "store"
        slug, n = base, 1
        while Store.all_objects.filter(slug=slug).exclude(pk=self.pk).exists():
            n += 1
            slug = f"{base}-{n}"
        return slug

    def members(self):
        return self.memberships.select_related("user").filter(is_active=True)


class StoreMembership(TimeStampedModel):

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store_memberships",
    )
    role = models.CharField(
        max_length=20, choices=StoreRole.choices, default=StoreRole.ORDER_STAFF
    )

    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_memberships",
    )
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stores_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["store", "user"], name="uniq_store_user_membership"
            )
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def __str__(self):
        return f"{self.user} @ {self.store} ({self.role})"

    @property
    def rank(self):
        return ROLE_RANK.get(self.role, 99)

    @property
    def is_owner(self):
        return self.role == StoreRole.OWNER


class StoreSettings(TimeStampedModel):

    store = models.OneToOneField(
        Store, on_delete=models.CASCADE, related_name="settings"
    )

    delivery_charge_inside_dhaka = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("60.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    delivery_charge_outside_dhaka = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("120.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    district_charge_overrides = models.JSONField(default=dict, blank=True)

    free_delivery_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Order subtotal at or above which delivery is free. Blank = never.",
    )

    invoice_header = models.CharField(max_length=200, blank=True)
    invoice_footer_note = models.TextField(blank=True)
    invoice_terms = models.TextField(blank=True)
    show_discount_on_invoice = models.BooleanField(default=True)

    sms_on_confirmed = models.BooleanField(default=False)
    sms_on_shipped = models.BooleanField(default=False)
    sms_on_delivered = models.BooleanField(default=False)

    fraud_return_count_threshold = models.PositiveSmallIntegerField(default=3)
    fraud_return_rate_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("40.00"),
        help_text="Percent. Return rate at or above this flags the customer.",
    )

    cod_overdue_days = models.PositiveSmallIntegerField(default=7)

    class Meta:
        db_table = "stores_settings"
        verbose_name_plural = "store settings"

    def __str__(self):
        return f"Settings for {self.store}"

    def delivery_charge_for(self, district):
        if district:
            override = self.district_charge_overrides.get(district)
            if override is not None:
                return Decimal(str(override))
            if district.strip().lower() == "dhaka":
                return self.delivery_charge_inside_dhaka
        return self.delivery_charge_outside_dhaka


class StoreInvitation(TimeStampedModel):

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20, choices=StoreRole.choices, default=StoreRole.ORDER_STAFF
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stores_invitation"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "email"])]

    def __str__(self):
        return f"Invite {self.email} -> {self.store} ({self.role})"

    @property
    def is_accepted(self):
        return self.accepted_at is not None

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() > self.expires_at

    @property
    def is_usable(self):
        return not self.is_accepted and not self.is_expired
