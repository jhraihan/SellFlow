from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "store", "notification_type", "level",
                    "is_read", "created_at"]
    list_filter = ["notification_type", "level", "is_read"]
    search_fields = ["title", "body", "store__name"]
    date_hierarchy = "created_at"
