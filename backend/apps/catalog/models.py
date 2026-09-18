from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class Category(StoreOwnedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_category"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "slug"], name="uniq_store_category_slug"
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_slug()
        super().save(*args, **kwargs)

    def _generate_slug(self):
        base = slugify(self.name) or "category"
        slug, n = base, 1
        siblings = Category.objects.filter(store_id=self.store_id)
        while siblings.filter(slug=slug).exclude(pk=self.pk).exists():
            n += 1
            slug = f"{base}-{n}"
        return slug


class ProductQuerySet(StoreScopedQuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_stock(self):
        return self.prefetch_related("stock_items", "variants")

    def low_stock(self):
        return self.filter(
            stock_items__on_hand__lte=models.F("low_stock_threshold")
        ).distinct()


class Product(StoreOwnedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    sku = models.CharField(max_length=64, blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    description = models.TextField(blank=True)

    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    weight_grams = models.PositiveIntegerField(default=0)

    has_variants = models.BooleanField(default=False)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table = "catalog_product"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "sku"], name="uniq_store_product_sku"
            )
        ]
        indexes = [
            models.Index(fields=["store", "is_active"]),
            models.Index(fields=["store", "name"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        base = slugify(self.name).upper().replace("-", "")[:8] or "SKU"
        siblings = Product.objects.filter(store_id=self.store_id)
        n = 1
        candidate = f"{base}-{n:04d}"
        while siblings.filter(sku=candidate).exclude(pk=self.pk).exists():
            n += 1
            candidate = f"{base}-{n:04d}"
        return candidate

    @property
    def margin(self):
        return self.selling_price - self.cost_price

    @property
    def margin_percent(self):
        if not self.selling_price:
            return Decimal("0.00")
        return ((self.margin / self.selling_price) * 100).quantize(Decimal("0.01"))


class ProductImage(models.Model):
    MAX_PER_PRODUCT = 6

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=150, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_product_image"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductVariant(StoreOwnedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    sku = models.CharField(max_length=64, blank=True)

    option1_name = models.CharField(max_length=40, blank=True)
    option1_value = models.CharField(max_length=60, blank=True)
    option2_name = models.CharField(max_length=40, blank=True)
    option2_value = models.CharField(max_length=60, blank=True)

    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    cost_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_product_variant"
        ordering = ["option1_value", "option2_value"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "sku"], name="uniq_store_variant_sku"
            )
        ]

    def __str__(self):
        return f"{self.product.name} - {self.label}"

    def save(self, *args, **kwargs):
        if not self.store_id and self.product_id:
            self.store_id = self.product.store_id
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        parts = [self.product.sku]
        if self.option1_value:
            parts.append(slugify(self.option1_value).upper()[:6])
        if self.option2_value:
            parts.append(slugify(self.option2_value).upper()[:6])
        base = "-".join(p for p in parts if p)
        siblings = ProductVariant.objects.filter(store_id=self.store_id)
        candidate, n = base, 1
        while siblings.filter(sku=candidate).exclude(pk=self.pk).exists():
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    @property
    def label(self):
        bits = [v for v in (self.option1_value, self.option2_value) if v]
        return " / ".join(bits) or "Default"

    @property
    def selling_price(self):
        if self.price_override is not None:
            return self.price_override
        return self.product.selling_price

    @property
    def cost_price(self):
        if self.cost_override is not None:
            return self.cost_override
        return self.product.cost_price

    @property
    def weight(self):
        if self.weight_grams is not None:
            return self.weight_grams
        return self.product.weight_grams


class StockItem(StoreOwnedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stock_items"
    )
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_item",
    )

    on_hand = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)

    class Meta:
        db_table = "catalog_stock_item"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant"],
                name="uniq_product_variant_stock",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(variant__isnull=True),
                name="uniq_product_stock_without_variant",
            ),
            models.CheckConstraint(
                condition=models.Q(on_hand__gte=0), name="stock_on_hand_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(reserved__gte=0),
                name="stock_reserved_non_negative",
            ),
        ]

    def __str__(self):
        target = self.variant.label if self.variant else "default"
        return f"{self.product.name} [{target}]: {self.available} available"

    @property
    def available(self):
        return self.on_hand - self.reserved

    @property
    def is_low(self):
        return self.available <= self.product.low_stock_threshold


class MovementType(models.TextChoices):
    PURCHASE = "purchase", "Purchase / restock"
    ORDER_RESERVE = "order_reserve", "Reserved for order"
    RESERVE_RELEASE = "reserve_release", "Reservation released"
    SALE = "sale", "Shipped / sold"
    RETURN_RESTOCK = "return_restock", "Returned to stock"
    WRITE_OFF = "write_off", "Written off"
    ADJUSTMENT = "adjustment", "Manual adjustment"


class StockMovement(StoreOwnedModel):
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="movements"
    )
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)

    quantity = models.IntegerField()
    on_hand_after = models.IntegerField()
    reserved_after = models.IntegerField()

    reference_type = models.CharField(max_length=30, blank=True)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    class Meta:
        db_table = "catalog_stock_movement"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["store", "stock_item", "-created_at"]),
            models.Index(fields=["store", "movement_type"]),
        ]

    def __str__(self):
        sign = "+" if self.quantity >= 0 else ""
        return f"{self.movement_type} {sign}{self.quantity}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "StockMovement rows are immutable and cannot be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("StockMovement rows are immutable and cannot be deleted.")
