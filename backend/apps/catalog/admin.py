from django.contrib import admin

from .models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    StockItem,
    StockMovement,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["sku", "option1_name", "option1_value", "option2_name",
              "option2_value", "price_override", "is_active"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "store", "parent", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "store__name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "store", "selling_price", "has_variants",
                    "is_active"]
    list_filter = ["is_active", "has_variants"]
    search_fields = ["name", "sku", "store__name"]
    inlines = [ProductImageInline, ProductVariantInline]


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ["product", "variant", "on_hand", "reserved", "available"]
    search_fields = ["product__name", "product__sku"]

    @admin.display(description="Available")
    def available(self, obj):
        return obj.available


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["stock_item", "movement_type", "quantity",
                    "on_hand_after", "actor", "created_at"]
    list_filter = ["movement_type"]
    search_fields = ["stock_item__product__name", "reason"]
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
