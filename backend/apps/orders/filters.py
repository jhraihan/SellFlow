from django_filters import rest_framework as filters

from .models import Order, OrderSource, OrderStatus, PaymentStatus


class OrderFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(
        field_name="status", choices=OrderStatus.choices
    )
    source = filters.MultipleChoiceFilter(
        field_name="source", choices=OrderSource.choices
    )
    payment_status = filters.MultipleChoiceFilter(
        field_name="payment_status", choices=PaymentStatus.choices
    )
    shipping_district = filters.CharFilter(lookup_expr="iexact")
    customer = filters.NumberFilter()

    class Meta:
        model = Order
        fields = [
            "status", "source", "payment_status",
            "shipping_district", "customer",
        ]
