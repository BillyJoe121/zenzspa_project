"""
Modelos base y utilidades para soft delete.
"""
import logging
import uuid

from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class BaseModel(models.Model):
    """Modelo base con ID UUID y timestamps automáticos."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet personalizado para soft delete."""

    def delete(self):
        """Soft delete: marca registros como eliminados sin borrarlos."""
        now_ts = timezone.now()
        with transaction.atomic():
            return super().update(
                is_deleted=True,
                deleted_at=now_ts,
                updated_at=now_ts,
            )

    def hard_delete(self):
        """Hard delete: elimina registros permanentemente."""
        return super().delete()

    def alive(self):
        """Filtra solo registros no eliminados."""
        return self.filter(is_deleted=False)

    def dead(self):
        """Filtra solo registros eliminados."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager personalizado para soft delete."""
    use_in_migrations = True

    def __init__(self, *args, include_deleted=False, **kwargs):
        self.include_deleted = include_deleted
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        if not self.include_deleted:
            qs = qs.filter(is_deleted=False)
        return qs

    def hard_delete(self):
        return self.get_queryset().hard_delete()


class SoftDeleteModel(BaseModel):
    """
    Modelo base con soft delete.

    Proporciona eliminación lógica en lugar de física, permitiendo
    recuperación de registros y manteniendo integridad referencial.
    """
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager(include_deleted=True)

    class Meta(BaseModel.Meta):
        abstract = True
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def delete(self, using=None, keep_parents=False):
        """
        Soft delete atómico para prevenir race conditions.

        Usa all_objects (incluye eliminados) para evitar DoesNotExist
        si otro thread ya marcó como eliminado. Maneja gracefully
        deletes concurrentes siendo idempotente.
        """
        if self.is_deleted:
            return

        with transaction.atomic():
            try:
                # Usar all_objects para incluir registros ya eliminados
                fresh = type(self).all_objects.select_for_update().get(pk=self.pk)

                # Si ya fue eliminado por otro thread, salir silenciosamente
                if fresh.is_deleted:
                    return

                fresh.is_deleted = True
                fresh.deleted_at = timezone.now()
                fresh.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

            except type(self).DoesNotExist:
                # El objeto ya fue hard-deleted, no hacer nada
                logger.warning(
                    "Intento de soft-delete en objeto ya eliminado: %s pk=%s",
                    type(self).__name__,
                    self.pk
                )
                return

    def hard_delete(self, using=None, keep_parents=False):
        """Eliminación física permanente del registro."""
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restaura un registro eliminado lógicamente."""
        if not self.is_deleted:
            return
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
