"""
Abstract base models shared across the project.

`StoreOwnedModel` is the tenancy boundary: every business table inherits
from it, and its default manager refuses to hand back rows without an
explicit store filter. Isolation is structural, not something each
viewset has to remember (PRD: Data integrity rules, Risk "Multi-tenant
data leakage").
"""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Adds created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """Soft-delete the whole queryset."""
        from django.utils import timezone

        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """
    Default manager that hides soft-deleted rows.

    Filtering in `get_queryset` rather than relying on callers to add
    `.alive()` is what makes the guarantee hold everywhere, including
    related lookups and get_object_or_404.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def with_deleted(self):
        """Escape hatch: every row, including soft-deleted ones."""
        return super().get_queryset()


class SoftDeleteModel(models.Model):
    """
    Records that must survive for audit are never really removed.

    The default manager hides soft-deleted rows; `all_objects` exposes them.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self._write_deleted_at()

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self._write_deleted_at()

    def _write_deleted_at(self):
        """
        Persist `deleted_at` through an unfiltered manager.

        The default manager hides soft-deleted rows, so a normal
        `save(update_fields=...)` on an already-deleted instance would
        match zero rows and raise. Writing via the base queryset keeps
        delete() and restore() symmetrical.
        """
        from django.utils import timezone

        type(self)._base_unfiltered().filter(pk=self.pk).update(
            deleted_at=self.deleted_at, updated_at=timezone.now()
        )

    @classmethod
    def _base_unfiltered(cls):
        """The manager that can see soft-deleted rows."""
        manager = getattr(cls, "all_objects", None)
        if manager is not None:
            return manager
        return cls._default_manager.with_deleted()

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class StoreScopedQuerySet(models.QuerySet):
    """Queryset that makes the tenant filter explicit."""

    def for_store(self, store):
        """
        Restrict to one store. `store` may be a Store instance or its pk.

        This is the only sanctioned way to read store-owned data.
        """
        if store is None:
            return self.none()
        store_id = getattr(store, "pk", store)
        return self.filter(store_id=store_id)

    def for_stores(self, stores):
        """Restrict to several stores (a user may belong to more than one)."""
        ids = [getattr(s, "pk", s) for s in stores]
        if not ids:
            return self.none()
        return self.filter(store_id__in=ids)


class StoreOwnedModel(TimeStampedModel):
    """
    Base for every table that belongs to a single store.

    Subclasses get a `store` FK and a queryset with `.for_store()`. Views
    must go through `StoreScopedMixin` (see apps.core.mixins), which
    applies the filter for them.
    """

    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = StoreScopedQuerySet.as_manager()

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Adds a public, non-enumerable identifier for externally shared URLs."""

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True
