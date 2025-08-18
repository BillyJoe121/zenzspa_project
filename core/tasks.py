from __future__ import annotations
from celery import shared_task
from django.utils.timezone import now

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
