from __future__ import annotations
from celery import shared_task
from django.utils.timezone import now
from datetime import timedelta

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_transactional_email(self, template_key: str, to_email: str, context: dict):
    # Aquí solo el esqueleto; la app de notificaciones hará el trabajo real.
    # La gracia es tener la firma unificada y manejada por Celery.
    return {
        "sent_at": now().isoformat(),
        "template_key": template_key,
        "to": to_email,
        "context": context,
    }


@shared_task
def cleanup_old_idempotency_keys():
    """
    Elimina claves de idempotencia completadas hace más de 7 días.
    También limpia claves pendientes muy antiguas (posibles fallos).
    Ejecutar diariamente vía Celery Beat.
    """
    from .models import IdempotencyKey
    
    cutoff = now() - timedelta(days=7)
    deleted_count, _ = IdempotencyKey.objects.filter(
        status=IdempotencyKey.Status.COMPLETED,
        completed_at__lt=cutoff
    ).delete()
    
    # También limpiar claves pendientes muy antiguas (posibles fallos)
    stale_cutoff = now() - timedelta(hours=24)
    stale_count, _ = IdempotencyKey.objects.filter(
        status=IdempotencyKey.Status.PENDING,
        locked_at__lt=stale_cutoff
    ).delete()
    
    return {
        "deleted_completed": deleted_count,
        "deleted_stale": stale_count
    }
