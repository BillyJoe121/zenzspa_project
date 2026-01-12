"""
Vistas administrativas para marcar usuarios como Persona Non Grata.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.models import AdminNotification, AuditLog
from notifications.services import NotificationService
from spa.models import Appointment

from ..models import BlockedPhoneNumber, CustomUser, UserSession
from ..serializers import FlagNonGrataSerializer
from ..throttling import AdminRateThrottle

logger = logging.getLogger(__name__)


class FlagNonGrataView(generics.UpdateAPIView):
    """Marca un usuario como Persona Non Grata (CNG)."""

    queryset = CustomUser.objects.all()
    serializer_class = FlagNonGrataSerializer
    permission_classes = [IsAdminUser]
    throttle_classes = [AdminRateThrottle]
    lookup_field = 'phone_number'

    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()
        new_unusable_password = get_random_string(length=16)
        now = timezone.now()

        # Cancelar todas las citas futuras
        future_appointments = Appointment.objects.filter(
            user=instance,
            start_time__gte=now,
            status__in=[
                Appointment.AppointmentStatus.CONFIRMED,
                Appointment.AppointmentStatus.PENDING_PAYMENT,
                Appointment.AppointmentStatus.RESCHEDULED,
                Appointment.AppointmentStatus.FULLY_PAID,
            ],
        )
        future_appointments.update(
            status=Appointment.AppointmentStatus.CANCELLED,
            outcome=Appointment.AppointmentOutcome.CANCELLED_BY_ADMIN,
        )

        # Registrar en audit log
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=instance,
            action=AuditLog.Action.FLAG_NON_GRATA,
            details=f"Usuario marcado como Persona Non Grata. Notas: {serializer.validated_data.get('internal_notes', 'N/A')}"
        )

        # Crear notificación admin
        AdminNotification.objects.create(
            title="Usuario marcado como CNG",
            message=f"El usuario {instance.phone_number} fue bloqueado por {self.request.user.get_full_name() or self.request.user.phone_number}.",
            notification_type=AdminNotification.NotificationType.USUARIOS,
            subtype=AdminNotification.NotificationSubtype.USUARIO_CNG,
        )

        # Actualizar usuario
        instance.is_persona_non_grata = True
        instance.is_active = False
        instance.set_password(new_unusable_password)

        instance.internal_notes = serializer.validated_data.get('internal_notes', instance.internal_notes)
        instance.internal_photo_url = serializer.validated_data.get('internal_photo_url', instance.internal_photo_url)

        # Bloquear número de teléfono
        BlockedPhoneNumber.objects.update_or_create(
            phone_number=instance.phone_number,
            defaults={
                'notes': serializer.validated_data.get('internal_notes', instance.internal_notes) or ''
            },
        )

        # Invalidar todos los tokens JWT
        tokens = OutstandingToken.objects.filter(user=instance)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                continue

        # Invalidar todas las sesiones activas
        invalidated_sessions = UserSession.objects.filter(
            user=instance,
            is_active=True
        ).update(is_active=False)

        if invalidated_sessions:
            logger.info(
                "Usuario CNG: %d sesiones invalidadas para %s",
                invalidated_sessions,
                instance.phone_number
            )

        instance.save()

        # Enviar notificación al usuario
        try:
            admin_url = f"{settings.SITE_URL.rstrip('/')}/admin/users/customuser/{instance.id}/change/"
            NotificationService.send_notification(
                user=instance,
                event_code="USER_FLAGGED_NON_GRATA",
                context={
                    "user_name": instance.get_full_name()
                    or instance.first_name
                    or "Cliente",
                    "user_email": instance.email or "No disponible",
                    "user_phone": instance.phone_number,
                    "flag_reason": serializer.validated_data.get("internal_notes")
                    or instance.internal_notes
                    or "Motivo no especificado",
                    "action_taken": "Acceso bloqueado y sesiones terminadas",
                    "admin_url": admin_url,
                },
                priority="high",
            )
        except Exception:
            logger.exception("No se pudo notificar al usuario %s sobre su estado CNG", instance.phone_number)
