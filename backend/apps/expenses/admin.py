from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["date", "store", "category", "amount", "campaign_name",
                    "created_by"]
    list_filter = ["category"]
    search_fields = ["note", "campaign_name", "store__name"]
    date_hierarchy = "date"
