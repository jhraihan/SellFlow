
from django.db import transaction
from rest_framework import serializers

from apps.stores.permissions import Cap, role_has

from .models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    StockItem,
    StockMovement,
)
from .services import get_or_create_stock_item


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "is_active", "product_count"]
        read_only_fields = ["id", "slug"]

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()

    def validate_parent(self, value):
        if value is None:
            return value
        store = self.context.get("store")
        if store and value.store_id != store.id:
            raise serializers.ValidationError("Unknown category.")
        if value.parent_id is not None:
            raise serializers.ValidationError(
                "Categories may only nest one level deep."
            )
        return value


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "sort_order", "is_primary"]
        read_only_fields = ["id"]


class StockItemSerializer(serializers.ModelSerializer):
    available = serializers.IntegerField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = ["id", "on_hand", "reserved", "available", "is_low"]
        read_only_fields = fields


class ProductVariantSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    selling_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id", "sku", "label",
            "option1_name", "option1_value",
            "option2_name", "option2_value",
            "price_override", "cost_override", "weight_grams",
            "selling_price", "is_active", "stock",
        ]
        read_only_fields = ["id", "label", "selling_price"]

    def get_stock(self, obj):
        item = getattr(obj, "stock_item", None)
        if item is None:
            return None
        return StockItemSerializer(item).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._may_see_cost():
            data.pop("cost_override", None)
        return data

    def _may_see_cost(self):
        membership = self.context.get("membership")
        if membership is None:
            return False
        return role_has(membership.role, Cap.VIEW_COST_PRICE)


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()
    variant_count = serializers.IntegerField(
        source="variants.count", read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "category", "category_name",
            "selling_price", "cost_price", "has_variants", "variant_count",
            "low_stock_threshold", "is_active", "primary_image",
            "total_stock", "created_at",
        ]

    def get_primary_image(self, obj):
        image = next(
            (i for i in obj.images.all() if i.is_primary), None
        ) or next(iter(obj.images.all()), None)
        if image is None:
            return None
        request = self.context.get("request")
        url = image.image.url
        return request.build_absolute_uri(url) if request else url

    def get_total_stock(self, obj):
        items = obj.stock_items.all()
        return {
            "on_hand": sum(i.on_hand for i in items),
            "reserved": sum(i.reserved for i in items),
            "available": sum(i.available for i in items),
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._may_see_cost():
            data.pop("cost_price", None)
        return data

    def _may_see_cost(self):
        membership = self.context.get("membership")
        if membership is None:
            return False
        return role_has(membership.role, Cap.VIEW_COST_PRICE)


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    stock = serializers.SerializerMethodField()
    margin = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    margin_percent = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "slug", "description", "weight_grams",
            "images", "variants", "stock", "margin", "margin_percent",
        ]

    def get_stock(self, obj):
        if obj.has_variants:
            return None
        item = obj.stock_items.filter(variant__isnull=True).first()
        return StockItemSerializer(item).data if item else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._may_see_cost():
            data.pop("margin", None)
            data.pop("margin_percent", None)
        return data


class ProductWriteSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, required=False)
    opening_stock = serializers.IntegerField(
        required=False, min_value=0, write_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "category", "description",
            "selling_price", "cost_price", "weight_grams",
            "has_variants", "low_stock_threshold", "is_active",
            "variants", "opening_stock",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Product name is too short.")
        return value

    def validate_category(self, value):
        if value is None:
            return value
        store = self.context.get("store")
        if store and value.store_id != store.id:
            raise serializers.ValidationError("Unknown category.")
        return value

    def validate_sku(self, value):
        if not value:
            return value
        value = value.strip().upper()
        store = self.context.get("store")
        if store:
            clash = Product.objects.filter(store=store, sku=value)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    "Another product already uses this SKU."
                )
        return value

    def validate(self, attrs):
        variants = attrs.get("variants") or []
        has_variants = attrs.get(
            "has_variants",
            getattr(self.instance, "has_variants", False),
        )

        if has_variants and not variants and self.instance is None:
            raise serializers.ValidationError(
                {"variants": "Add at least one variant, or set has_variants to false."}
            )
        if variants and not has_variants:
            raise serializers.ValidationError(
                {"has_variants": "Set has_variants to true when supplying variants."}
            )
        if has_variants and attrs.get("opening_stock"):
            raise serializers.ValidationError(
                {"opening_stock": "Set stock per variant, not on the product."}
            )

        seen = set()
        for variant in variants:
            key = (
                variant.get("option1_value", ""),
                variant.get("option2_value", ""),
            )
            if key in seen:
                raise serializers.ValidationError(
                    {"variants": f"Duplicate variant combination: {key}."}
                )
            seen.add(key)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        variants = validated_data.pop("variants", [])
        opening = validated_data.pop("opening_stock", 0)
        store = self.context["store"]

        product = Product.objects.create(store=store, **validated_data)

        if variants:
            for row in variants:
                variant = ProductVariant.objects.create(
                    store=store, product=product, **row
                )
                get_or_create_stock_item(product, variant)
        else:
            item = get_or_create_stock_item(product, None)
            if opening:
                from .services import receive_stock

                receive_stock(
                    item,
                    opening,
                    actor=self.context["request"].user,
                    reason="Opening stock",
                )
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("variants", None)
        validated_data.pop("opening_stock", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class StockAdjustSerializer(serializers.Serializer):
    stock_item = serializers.IntegerField()
    new_on_hand = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=200)

    def validate_stock_item(self, value):
        store = self.context["store"]
        item = StockItem.objects.filter(pk=value, store=store).first()
        if item is None:
            raise serializers.ValidationError("Unknown stock item.")
        self.context["item"] = item
        return value

    def validate_reason(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError(
                "Give a short reason for the adjustment."
            )
        return value


class StockReceiveSerializer(serializers.Serializer):
    stock_item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_stock_item(self, value):
        store = self.context["store"]
        item = StockItem.objects.filter(pk=value, store=store).first()
        if item is None:
            raise serializers.ValidationError("Unknown stock item.")
        self.context["item"] = item
        return value


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="stock_item.product.name", read_only=True
    )
    variant_label = serializers.SerializerMethodField()
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    movement_type_display = serializers.CharField(
        source="get_movement_type_display", read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "id", "stock_item", "product_name", "variant_label",
            "movement_type", "movement_type_display", "quantity",
            "on_hand_after", "reserved_after",
            "reference_type", "reference_id", "reason",
            "actor_name", "created_at",
        ]
        read_only_fields = fields

    def get_variant_label(self, obj):
        variant = obj.stock_item.variant
        return variant.label if variant else None


class StockLevelSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.SerializerMethodField()
    variant_label = serializers.SerializerMethodField()
    available = serializers.IntegerField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)
    low_stock_threshold = serializers.IntegerField(
        source="product.low_stock_threshold", read_only=True
    )

    class Meta:
        model = StockItem
        fields = [
            "id", "product_id", "product_name", "sku", "variant_label",
            "on_hand", "reserved", "available", "is_low", "low_stock_threshold",
        ]
        read_only_fields = fields

    def get_sku(self, obj):
        return obj.variant.sku if obj.variant else obj.product.sku

    def get_variant_label(self, obj):
        return obj.variant.label if obj.variant else None
