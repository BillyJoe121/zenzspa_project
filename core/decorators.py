from functools import wraps
import hashlib
import json

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from .models import IdempotencyKey


def idempotent_view(timeout=60):
    """
    Decorator that enforces idempotency for POST handlers using the Idempotency-Key header.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(self, request, *args, **kwargs):
            method = getattr(request, "method", "").upper()
            allowed_methods = {"POST", "PUT", "PATCH", "DELETE"}
            if method not in allowed_methods:
                return view_func(self, request, *args, **kwargs)
            key = request.headers.get("Idempotency-Key")
            if not key:
                return view_func(self, request, *args, **kwargs)

            # Calcular hash del request body
            request_hash = ""
            if hasattr(request, 'data') and request.data:
                try:
                    request_hash = hashlib.sha256(
                        json.dumps(request.data, sort_keys=True).encode()
                    ).hexdigest()
                except (TypeError, ValueError):
                    pass

            user = request.user if request.user.is_authenticated else None

            with transaction.atomic():
                record, created = IdempotencyKey.objects.select_for_update().get_or_create(
                    key=key,
                    defaults={
                        "user": user,
                        "endpoint": request.path,
                        "status": IdempotencyKey.Status.PENDING,
                        "locked_at": timezone.now(),
                        "request_hash": request_hash,
                    },
                )
                if not created:
                    # Validar que el hash coincida
                    if record.request_hash and record.request_hash != request_hash:
                        return Response(
                            {
                                "detail": "La clave de idempotencia ya fue usada con datos diferentes.",
                                "code": "IDEMPOTENCY_KEY_MISMATCH"
                            },
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        )
                    if record.status == IdempotencyKey.Status.COMPLETED and record.response_body is not None:
                        return Response(record.response_body, status=record.status_code)

                    if record.status == IdempotencyKey.Status.PENDING:
                        if record.locked_at and (timezone.now() - record.locked_at).total_seconds() > timeout:
                            record.user = user
                            record.endpoint = request.path
                            record.locked_at = timezone.now()
                            record.response_body = None
                            record.status_code = None
                            record.status = IdempotencyKey.Status.PENDING
                            record.save(
                                update_fields=[
                                    "user",
                                    "endpoint",
                                    "locked_at",
                                    "response_body",
                                    "status_code",
                                    "status",
                                    "updated_at",
                                ]
                            )
                        else:
                            return Response(
                                {"detail": "Solicitud duplicada en proceso. Espera a que finalice."},
                                status=status.HTTP_409_CONFLICT,
                            )
                else:
                    record.locked_at = timezone.now()
                    record.save(update_fields=["locked_at", "updated_at"])

            try:
                response = view_func(self, request, *args, **kwargs)
            except Exception:
                with transaction.atomic():
                    IdempotencyKey.objects.filter(key=key).delete()
                raise

            payload = getattr(response, "data", None)
            with transaction.atomic():
                try:
                    record = IdempotencyKey.objects.select_for_update().get(key=key)
                except IdempotencyKey.DoesNotExist:
                    return response
                record.mark_completed(response_body=payload, status_code=response.status_code)

            return response

        return wrapped

    return decorator
