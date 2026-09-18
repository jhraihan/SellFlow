import uuid

from django.db import models


class TimeStampedModel(models.Model):

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
        from django.utils import timezone

        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def with_deleted(self):
        return super().get_queryset()


class SoftDeleteModel(models.Model):

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
        from django.utils import timezone

        type(self)._base_unfiltered().filter(pk=self.pk).update(
            deleted_at=self.deleted_at, updated_at=timezone.now()
        )

    @classmethod
    def _base_unfiltered(cls):
        manager = getattr(cls, "all_objects", None)
        if manager is not None:
            return manager
        return cls._default_manager.with_deleted()

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class StoreScopedQuerySet(models.QuerySet):

    def for_store(self, store):
        if store is None:
            return self.none()
        store_id = getattr(store, "pk", store)
        return self.filter(store_id=store_id)

    def for_stores(self, stores):
        ids = [getattr(s, "pk", s) for s in stores]
        if not ids:
            return self.none()
        return self.filter(store_id__in=ids)


class StoreOwnedModel(TimeStampedModel):

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

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True
