"""
Vistas administrativas: gestión de usuarios, exportación, bloqueos.
"""
import csv
import logging

from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.crypto import get_random_string
from rest_framework import generics, status, views
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.models import AdminNotification, AuditLog
from notifications.services import NotificationService
from spa.models import Appointment

from ..models import BlockedPhoneNumber, CustomUser, UserSession
from ..permissions import IsStaffOrAdmin
from ..serializers import (
    FlagNonGrataSerializer,
    StaffListSerializer,
    UserExportSerializer,
)
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
            NotificationService.send_notification(
                user=instance,
                event_code="USER_FLAGGED_NON_GRATA",
                context={
                    "phone_number": instance.phone_number,
                    "notes": instance.internal_notes or "",
                },
                priority="high",
            )
        except Exception:
            logger.exception("No se pudo notificar al usuario %s sobre su estado CNG", instance.phone_number)


class StaffListView(generics.ListAPIView):
    """Lista todos los usuarios con rol de staff."""
    serializer_class = StaffListSerializer
    permission_classes = [IsStaffOrAdmin]

    def get_queryset(self):
        return CustomUser.objects.filter(role=CustomUser.Role.STAFF)


class BlockIPView(views.APIView):
    """Bloquea una IP temporalmente."""
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        ip = request.data.get("ip")
        ttl = int(request.data.get("ttl", 3600))

        if not ip:
            return Response({"detail": "IP requerida."}, status=status.HTTP_400_BAD_REQUEST)

        cache.set(f"blocked_ip:{ip}", True, timeout=ttl)
        return Response({"detail": f"IP {ip} bloqueada por {ttl} segundos."}, status=status.HTTP_200_OK)


class UserExportView(generics.ListAPIView):
    """Exporta usuarios en formato JSON o CSV."""
    permission_classes = [IsAdminUser]
    throttle_classes = [AdminRateThrottle]
    queryset = CustomUser.objects.all()
    serializer_class = UserExportSerializer

    def get(self, request, *args, **kwargs):
        if request.query_params.get('format') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="users_export.csv"'

            writer = csv.writer(response)
            writer.writerow(['ID', 'Phone', 'Email', 'First Name', 'Last Name', 'Role', 'Status', 'Created At'])

            for user in self.get_queryset():
                status_label = "Active" if user.is_active else "Inactive"
                if user.is_persona_non_grata:
                    status_label = "CNG"
                writer.writerow([
                    user.id, user.phone_number, user.email, user.first_name, user.last_name,
                    user.role, status_label, user.created_at
                ])
            return response
        return super().get(request, *args, **kwargs)
