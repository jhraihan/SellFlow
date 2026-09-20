from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import StoreOwnedModel, StoreScopedQuerySet


class ExpenseCategory(models.TextChoices):
    AD_SPEND = "ad_spend", "Ad spend"
    PACKAGING = "packaging", "Packaging"
    SALARY = "salary", "Salary"
    RENT = "rent", "Rent"
    COURIER_CHARGE = "courier_charge", "Courier charge"
    PRODUCT_PURCHASE = "product_purchase", "Product purchase"
    UTILITIES = "utilities", "Utilities"
    TRANSPORT = "transport", "Transport"
    OTHER = "other", "Other"


class ExpenseQuerySet(StoreScopedQuerySet):
    def in_period(self, date_from=None, date_to=None):
        queryset = self
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        return queryset


class Expense(StoreOwnedModel):
    date = models.DateField(db_index=True)
    category = models.CharField(
        max_length=30, choices=ExpenseCategory.choices
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    note = models.CharField(max_length=300, blank=True)
    attachment = models.FileField(
        upload_to="expenses/", null=True, blank=True
    )

    campaign_name = models.CharField(max_length=120, blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_expenses",
    )

    objects = ExpenseQuerySet.as_manager()

    class Meta:
        db_table = "expenses_expense"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["store", "-date"]),
            models.Index(fields=["store", "category"]),
        ]

    def __str__(self):
        return f"{self.category}: {self.amount} on {self.date}"
