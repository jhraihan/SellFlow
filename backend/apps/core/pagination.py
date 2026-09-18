"""Pagination classes (PRD API conventions)."""
from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Page-number pagination, the default for most endpoints."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class HighVolumeCursorPagination(CursorPagination):
    """
    Cursor pagination for large, frequently-appended tables (orders,
    customers) where page-number offsets get slow and can skip rows as
    new records arrive.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
