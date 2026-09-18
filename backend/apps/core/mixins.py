"""
Store-scoping for views.

Every store-owned viewset inherits `StoreScopedMixin`. It resolves which
store the caller is acting on, verifies membership, and filters the
queryset — so a view cannot accidentally serve another tenant's rows by
forgetting a filter.

Store resolution order:
  1. `X-Store-Id` header (a user may belong to several stores)
  2. the caller's single active membership, if they have exactly one
Anything else is ambiguous and is rejected.
"""
from apps.core.exceptions import StoreAccessDenied


class StoreContextMixin:
    """
    Resolves `request.store` and `request.membership`.

    Kept separate from queryset filtering so that views which are not
    themselves store-scoped (the store list, invitation acceptance) can
    still use the resolution logic.
    """

    store_header = "HTTP_X_STORE_ID"

    def initial(self, request, *args, **kwargs):
        request.store, request.membership = self._resolve_store(request)
        super().initial(request, *args, **kwargs)

    def _resolve_store(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return None, None

        from apps.stores.models import StoreMembership

        memberships = (
            StoreMembership.objects
            .select_related("store")
            .filter(user=user, is_active=True, store__deleted_at__isnull=True)
        )

        raw_id = request.META.get(self.store_header)
        if raw_id:
            try:
                store_id = int(raw_id)
            except (TypeError, ValueError):
                raise StoreAccessDenied(
                    "Invalid store identifier.",
                    details={"header": "X-Store-Id"},
                ) from None
            membership = memberships.filter(store_id=store_id).first()
            if membership is None:
                # Same response whether the store is missing or simply not
                # theirs: never confirm the existence of another tenant.
                raise StoreAccessDenied()
            return membership.store, membership

        found = list(memberships[:2])
        if len(found) == 1:
            return found[0].store, found[0]
        if not found:
            return None, None
        raise StoreAccessDenied(
            "You belong to several stores. Specify which one via the "
            "X-Store-Id header.",
            details={"header": "X-Store-Id"},
        )


class StoreScopedMixin(StoreContextMixin):
    """
    Filters the queryset to `request.store` and stamps it on create.

    Subclasses define `queryset` as usual; this narrows it. If no store
    resolved, the queryset is empty rather than unfiltered — failing
    closed is the point.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        store = getattr(self.request, "store", None)
        if store is None:
            return queryset.none()
        if hasattr(queryset, "for_store"):
            return queryset.for_store(store)
        return queryset.filter(store=store)

    def perform_create(self, serializer):
        store = getattr(self.request, "store", None)
        if store is None:
            raise StoreAccessDenied("No store selected for this request.")
        serializer.save(store=store)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["store"] = getattr(self.request, "store", None)
        context["membership"] = getattr(self.request, "membership", None)
        return context
