from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response

from users.models import CustomUser
from users.permissions import IsStaffOrAdmin
from core.models import AuditLog, GlobalSettings
from core.utils import safe_audit_log

from .models import ClinicalProfile, KioskSession
from .permissions import IsKioskSession, IsKioskSessionAllowExpired
from .serializers import KioskSessionStatusSerializer, KioskStartSessionSerializer

class KioskStartSessionView(generics.GenericAPIView):
    """
    Vista para que un STAFF inicie una sesión de Modo Quiosco para un cliente.
    """
    serializer_class = KioskStartSessionSerializer
    permission_classes = [IsStaffOrAdmin]

    def post(self, request, *args, **kwargs):
        # CRÍTICO - Rate limiting: máximo 10 sesiones por hora por staff
        cache_key = f"kiosk_rate_limit:{request.user.id}"
        count = cache.get(cache_key, 0)

        if count >= 10:
            return Response(
                {
                    "detail": "Has excedido el límite de sesiones de kiosk por hora.",
                    "code": "KIOSK_RATE_LIMIT",
                    "retry_after": 3600
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        cache.set(cache_key, count + 1, timeout=3600)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_phone = serializer.validated_data['client_phone_number']
        try:
            client = CustomUser.objects.get(phone_number=client_phone)
        except CustomUser.DoesNotExist:
            return Response(
                {'detail': 'Cliente no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile, _ = ClinicalProfile.objects.get_or_create(user=client)
        staff_member = request.user

        timeout_minutes = getattr(settings, "KIOSK_SESSION_TIMEOUT_MINUTES", 5)

        # MEJORA #9: Usar timezone del spa desde GlobalSettings
        # Esto asegura que expires_at se calcula correctamente según la zona horaria del spa
        try:
            from datetime import timezone as dt_timezone

            settings_obj = GlobalSettings.load()
            spa_tz = ZoneInfo(settings_obj.timezone_display)
            now_spa = timezone.now().astimezone(spa_tz)
            expires_at = now_spa + timedelta(minutes=timeout_minutes)
            expires_at_utc = expires_at.astimezone(dt_timezone.utc)

            expires_at = expires_at_utc
        except Exception as e:
            # Fallback a timezone por defecto si hay error
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "Error al obtener timezone del spa para kiosk session: %s. Usando UTC.",
                str(e)
            )
            expires_at = timezone.now() + timedelta(minutes=timeout_minutes)
        session = KioskSession.objects.create(
            profile=profile,
            staff_member=staff_member,
            expires_at=expires_at,
        )
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=staff_member,
            target_user=client,
            details={"kiosk_action": "start_session", "expires_at": expires_at.isoformat()},
        )
        return Response(
            {
                'kiosk_token': session.token,
                'session_id': str(session.id),
                'expires_at': session.expires_at.isoformat(),
                'status': session.status,
            },
            status=status.HTTP_201_CREATED,
        )


class KioskSessionStatusView(generics.GenericAPIView):
    permission_classes = [IsKioskSession]
    serializer_class = KioskSessionStatusSerializer

    def get(self, request, *args, **kwargs):
        session = request.kiosk_session
        if session.has_expired:
            session.mark_expired()
        serializer = self.get_serializer(session)
        return Response(serializer.data)


class KioskSessionHeartbeatView(generics.GenericAPIView):
    permission_classes = [IsKioskSessionAllowExpired]

    def post(self, request, *args, **kwargs):
        session = request.kiosk_session
        if session.has_expired:
            session.lock()
            return Response(
                {
                    "detail": "Sesión expirada. Mostrar pantalla segura.",
                    "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
                    "status": session.status,
                },
                status=440,
            )
        session.heartbeat()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "heartbeat"},
        )
        return Response(
            {
                "detail": "Heartbeat registrado.",
                "remaining_seconds": session.remaining_seconds,
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionLockView(generics.GenericAPIView):
    permission_classes = [IsKioskSession]

    def post(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.lock()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "lock"},
        )
        return Response(
            {
                "detail": "Sesión bloqueada.",
                "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
                "status": session.status,
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionDiscardChangesView(generics.GenericAPIView):
    permission_classes = [IsKioskSession]

    def post(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.lock()
        session.clear_pending_changes()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "discard_changes"},
        )
        return Response(
            {
                "detail": "Cambios descartados y sesión finalizada.",
                "status": session.status,
                "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionSecureScreenView(generics.GenericAPIView):
    permission_classes = [IsKioskSessionAllowExpired]

    def post(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.lock()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "secure_screen"},
        )
        return Response(
            {
                "detail": "Pantalla segura activada.",
                "status": session.status,
                "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionPendingChangesView(generics.GenericAPIView):
    permission_classes = [IsKioskSession]

    def get(self, request, *args, **kwargs):
        session = request.kiosk_session
        return Response({"has_pending_changes": session.has_pending_changes}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.mark_pending_changes()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "mark_pending_changes"},
        )
        return Response({"has_pending_changes": True}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.clear_pending_changes()
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=getattr(request, "kiosk_staff", None),
            target_user=session.profile.user,
            details={"kiosk_action": "clear_pending_changes"},
        )
        return Response({"has_pending_changes": False}, status=status.HTTP_200_OK)


