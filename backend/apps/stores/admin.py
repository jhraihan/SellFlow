from django.contrib import admin

from .models import Store, StoreInvitation, StoreMembership, StoreSettings


class StoreMembershipInline(admin.TabularInline):
    model = StoreMembership
    extra = 0
    fields = ["user", "role", "is_active", "joined_at"]
    autocomplete_fields = ["user"]


class StoreSettingsInline(admin.StackedInline):
    model = StoreSettings
    extra = 0
    can_delete = False


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "district", "is_active", "created_at"]
    list_filter = ["is_active", "business_type"]
    search_fields = ["name", "slug", "owner__email"]
    readonly_fields = ["slug", "created_at", "updated_at", "deleted_at"]
    inlines = [StoreSettingsInline, StoreMembershipInline]

    def get_queryset(self, request):
        # Platform admins need to see soft-deleted stores for support.
        return Store.all_objects.all()


@admin.register(StoreMembership)
class StoreMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "store", "role", "is_active", "joined_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["user__email", "store__name"]
    autocomplete_fields = ["user", "store"]


@admin.register(StoreInvitation)
class StoreInvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "store", "role", "expires_at", "accepted_at"]
    list_filter = ["role"]
    search_fields = ["email", "store__name"]
    readonly_fields = ["token", "created_at", "updated_at"]
