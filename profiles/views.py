from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClinicalProfile, ConsentTemplate, ConsentDocument, DoshaQuestion, ClientDoshaAnswer, KioskSession
from spa.models import Appointment
from .permissions import (
    ClinicalProfileAccessPermission,
    IsKioskSession,
    IsKioskSessionAllowExpired,
    IsVerifiedUserOrKioskSession,
    load_kiosk_session_from_request,
)
from .serializers import (
    ClinicalProfileHistorySerializer,
    ClinicalProfileSerializer,
    ConsentTemplateSerializer,
    DoshaQuestionSerializer,
    DoshaQuizSubmissionSerializer,
    KioskSessionStatusSerializer,
    KioskStartSessionSerializer,
)
from .services import calculate_dominant_dosha_and_element
from users.models import CustomUser
from users.permissions import IsAdminUser, IsStaffOrAdmin, IsVerified
from core.models import AuditLog, GlobalSettings
from core.utils import get_client_ip, safe_audit_log

class ClinicalProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar Perfiles Clínicos (CRUD completo).
    Utiliza 'ClinicalProfileAccessPermission' para cumplir con RFD-CLI-02.
    """
    queryset = ClinicalProfile.objects.select_related('user').prefetch_related('pains', 'dosha_answers')
    serializer_class = ClinicalProfileSerializer
    permission_classes = [IsVerifiedUserOrKioskSession, ClinicalProfileAccessPermission]
    STAFF_LOOKBACK_DAYS = 30
    STAFF_ALLOWED_STATUSES = {
        Appointment.AppointmentStatus.PENDING_PAYMENT,
        Appointment.AppointmentStatus.PAID,
        Appointment.AppointmentStatus.CONFIRMED,
        Appointment.AppointmentStatus.RESCHEDULED,
        Appointment.AppointmentStatus.COMPLETED,
    }
    
    lookup_field = 'user__phone_number'
    lookup_url_kwarg = 'phone_number'

    def get_queryset(self):
        base_queryset = self.queryset
        kiosk_client = getattr(self.request, 'kiosk_client', None)
        if kiosk_client:
            return base_queryset.filter(user=kiosk_client)
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return base_queryset.none()
        if user.role == CustomUser.Role.ADMIN:
            return base_queryset
        if user.role == CustomUser.Role.STAFF:
            allowed_user_ids = self._get_staff_allowed_users(user)
            if not allowed_user_ids:
                return base_queryset.none()
            return base_queryset.filter(user_id__in=allowed_user_ids)
        return base_queryset.filter(user=user)

    def _get_staff_allowed_users(self, staff_user):
        """Restringe acceso a perfiles de pacientes asignados a citas recientes o próximas."""
        now = timezone.now()
        window_start = now - timedelta(days=self.STAFF_LOOKBACK_DAYS)
        window_end = now + timedelta(days=self.STAFF_LOOKBACK_DAYS)
        return Appointment.objects.filter(
            staff_member=staff_user,
            start_time__range=(window_start, window_end),
            status__in=self.STAFF_ALLOWED_STATUSES,
        ).values_list('user_id', flat=True).distinct()


    def retrieve(self, request, *args, **kwargs):
        """Sobrescribir para auditar acceso a datos médicos"""
        instance = self.get_object()
        
        # Auditar acceso a perfil médico (HIPAA Compliance)
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=request.user if request.user.is_authenticated else None,
            target_user=instance.user,
            details={
                "action": "view_clinical_profile",
                "profile_id": str(instance.id),
                "accessed_by_role": getattr(request.user, 'role', 'UNKNOWN'),
                "kiosk_session": bool(getattr(request, 'kiosk_session', None)),
            }
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def get_object(self):
        phone_number = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset()
        filter_kwargs = {self.lookup_field: phone_number}
        obj = get_object_or_404(queryset, **filter_kwargs)
        kiosk_client = getattr(self.request, 'kiosk_client', None)
        if kiosk_client and obj.user != kiosk_client:
            raise PermissionDenied("La sesión de quiosco no puede acceder a este perfil.")
        return obj


    def update(self, request, *args, **kwargs):
        """Sobrescribir para auditar modificaciones a datos médicos"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Capturar datos antes de actualizar
        old_data = {
            'medical_conditions': instance.medical_conditions,
            'allergies': instance.allergies,
            'contraindications': instance.contraindications,
        }
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Auditar cambios en campos sensibles
        changes = []
        for field in ['medical_conditions', 'allergies', 'contraindications']:
            if old_data[field] != getattr(instance, field):
                changes.append(field)
        
        if changes:
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                admin_user=request.user if request.user.is_authenticated else None,
                target_user=instance.user,
                details={
                    "action": "update_clinical_profile",
                    "profile_id": str(instance.id),
                    "fields_modified": changes,
                    "kiosk_session": bool(getattr(request, 'kiosk_session', None)),
                }
            )
        
        return Response(serializer.data)

    def perform_update(self, serializer):
        instance = serializer.save()
        kiosk_session = getattr(self.request, 'kiosk_session', None)
        if kiosk_session:
            kiosk_session.clear_pending_changes()
        return instance

    # Se añade una acción personalizada para el endpoint /me/
    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request, *args, **kwargs):
        """
        Endpoint para que el usuario autenticado vea o actualice su propio perfil.
        """
        # Obtenemos el perfil del usuario que hace la petición
        profile_owner = getattr(request, 'kiosk_client', None) or request.user
        if not profile_owner or not getattr(profile_owner, 'is_authenticated', True):
            raise PermissionDenied("No se pudo determinar el perfil del usuario.")
        profile = get_object_or_404(ClinicalProfile, user=profile_owner)
        
        if request.method == 'GET':
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        
        # Para PUT y PATCH, la lógica es de actualización
        serializer = self.get_serializer(profile, data=request.data, partial=request.method == 'PATCH')
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class DoshaQuestionViewSet(viewsets.ModelViewSet):
    queryset = DoshaQuestion.objects.all().prefetch_related('options')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsAdminUser]


class ConsentTemplateViewSet(viewsets.ModelViewSet):
    queryset = ConsentTemplate.objects.all()
    serializer_class = ConsentTemplateSerializer
    permission_classes = [IsAdminUser]


class DoshaQuestionListView(generics.ListAPIView):
    queryset = DoshaQuestion.objects.all().prefetch_related('options').order_by('category', 'created_at')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsVerified]

# --- INICIO DE LA MODIFICACIÓN ---
# Se modifica la vista para que acepte tanto sesiones de usuario como de quiosco.

class DoshaQuizSubmitView(generics.GenericAPIView):
    serializer_class = DoshaQuizSubmissionSerializer
    # Se reemplaza el permiso anterior por nuestra nueva clase de permiso compuesta.
    permission_classes = [IsVerifiedUserOrKioskSession]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answers_data = serializer.validated_data.get('answers', [])

        # CRÍTICO - Validar que se respondieron todas las preguntas
        total_questions = DoshaQuestion.objects.count()
        answered_questions = len(set(a['question_id'] for a in answers_data))

        if answered_questions < total_questions:
            return Response(
                {
                    "detail": f"Debes responder todas las preguntas. Respondidas: {answered_questions}/{total_questions}",
                    "code": "QUIZ_INCOMPLETE",
                    "missing_count": total_questions - answered_questions
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Lógica bimodal: Determinar el perfil a actualizar.
        kiosk_session = getattr(request, 'kiosk_session', None)
        if hasattr(request, 'kiosk_client'):
            # MODO QUIOSCO: La petición fue validada por IsKioskSession,
            # que adjuntó el cliente a la petición.
            profile_owner = request.kiosk_client
        else:
            # MODO ESTÁNDAR: La petición fue validada por IsVerified.
            # El perfil a actualizar es el del usuario logueado.
            profile_owner = request.user

        # Obtenemos el perfil clínico del usuario determinado.
        # Usamos get_or_create para asegurar que el perfil exista.
        profile, _ = ClinicalProfile.objects.get_or_create(user=profile_owner)

        with transaction.atomic():
            # El resto de la lógica es idéntica, solo que ahora usa el 'profile' correcto.
            ClientDoshaAnswer.objects.filter(profile=profile).delete()
            answers_to_create = [
                ClientDoshaAnswer(
                    profile=profile,
                    question_id=answer['question_id'],
                    selected_option_id=answer['selected_option_id']
                )
                for answer in answers_data
            ]
            ClientDoshaAnswer.objects.bulk_create(answers_to_create)

        # La llamada al servicio para calcular el resultado se mantiene igual.
        # Nuestro sistema de señales se encargará del resto automáticamente.
        result = calculate_dominant_dosha_and_element(profile.id)

        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        # Si la sesión es de quiosco, podríamos invalidar el token aquí
        # para que no se pueda usar de nuevo.
        if kiosk_session:
            safe_audit_log(
                action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
                admin_user=getattr(request, "kiosk_staff", None),
                target_user=profile.user,
                details={"kiosk_action": "dosha_quiz_submit"},
            )
            kiosk_session.deactivate()

        return Response(result, status=status.HTTP_200_OK)

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
    permission_classes = [IsKioskSession]

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


class ClinicalProfileHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provee acceso de solo lectura al historial versionado de los perfiles.
    """

    permission_classes = [IsAuthenticated, IsStaffOrAdmin]
    serializer_class = ClinicalProfileHistorySerializer
    from rest_framework.pagination import PageNumberPagination
    class StandardResultsSetPagination(PageNumberPagination):
        page_size = 10
        page_size_query_param = 'page_size'
        max_page_size = 100
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = ClinicalProfile.history.select_related('history_user')
        profile_id = self.request.query_params.get('profile_id')
        if profile_id:
            queryset = queryset.filter(id=profile_id)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        return queryset.order_by('-history_date')


class AnonymizeProfileView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, phone_number, *args, **kwargs):
        profile = get_object_or_404(
            ClinicalProfile.objects.select_related('user'),
            user__phone_number=phone_number,
        )
        profile.anonymize(performed_by=request.user)
        return Response({"detail": "Perfil anonimizado correctamente."}, status=status.HTTP_200_OK)


class SignConsentView(generics.GenericAPIView):
    """
    Endpoint para que un usuario firme un consentimiento.
    CRÍTICO: Captura IP real del cliente para cumplimiento legal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')

        if not template_id:
            return Response(
                {"detail": "El campo 'template_id' es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            template = ConsentTemplate.objects.get(id=template_id, is_active=True)
        except ConsentTemplate.DoesNotExist:
            return Response(
                {"detail": "Template de consentimiento no encontrado o inactivo."},
                status=status.HTTP_404_NOT_FOUND
            )

        profile, _ = ClinicalProfile.objects.get_or_create(user=request.user)

        # CRÍTICO - Capturar IP real del cliente
        client_ip = get_client_ip(request)

        # Verificar si ya existe un consentimiento firmado
        existing_consent = ConsentDocument.objects.filter(
            profile=profile,
            template_version=template.version,
            is_signed=True
        ).first()

        if existing_consent:
            return Response(
                {
                    "detail": "Ya existe un consentimiento firmado para esta versión.",
                    "consent_id": str(existing_consent.id),
                    "signed_at": existing_consent.signed_at.isoformat()
                },
                status=status.HTTP_409_CONFLICT
            )

        # Crear consentimiento firmado
        consent = ConsentDocument.objects.create(
            profile=profile,
            template=template,
            is_signed=True,
            signed_at=timezone.now(),
            ip_address=client_ip,
            revoked_at=None,
            revoked_reason="",
            revoked_by=None,
        )

        # Auditar firma
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=request.user,
            details={
                "action": "sign_consent",
                "consent_id": str(consent.id),
                "template_version": template.version,
                "ip_address": client_ip,
            }
        )

        return Response(
            {
                "detail": "Consentimiento firmado exitosamente.",
                "consent_id": str(consent.id),
                "template_version": template.version,
                "signed_at": consent.signed_at.isoformat(),
                "signature_hash": consent.signature_hash
            },
            status=status.HTTP_201_CREATED
        )


class RevokeConsentView(generics.GenericAPIView):
    """
    Permite revocar un consentimiento firmado.
    Usuarios pueden revocar los suyos y el staff/admin puede revocar cualquiera.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, consent_id, *args, **kwargs):
        consent = get_object_or_404(
            ConsentDocument.objects.select_related("profile__user"),
            id=consent_id,
        )
        consent_owner = consent.profile.user
        user = request.user
        is_staff = user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]
        if consent_owner != user and not is_staff:
            raise PermissionDenied("No tienes permiso para revocar este consentimiento.")
        if not consent.is_signed:
            return Response(
                {"detail": "El consentimiento ya está revocado o pendiente."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get("reason", "")
        consent.is_signed = False
        consent.revoked_at = timezone.now()
        consent.revoked_reason = reason[:255] if reason else ""
        consent.revoked_by = user
        consent.save(update_fields=["is_signed", "revoked_at", "revoked_reason", "revoked_by", "updated_at"])
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=user if is_staff else None,
            target_user=consent_owner,
            details={
                "action": "revoke_consent",
                "consent_id": str(consent.id),
                "reason": consent.revoked_reason,
                "performed_by": str(user.id),
            },
        )
        return Response(
            {
                "detail": "Consentimiento revocado correctamente.",
                "consent_id": str(consent.id),
                "revoked_at": consent.revoked_at.isoformat(),
                "reason": consent.revoked_reason,
            },
            status=status.HTTP_200_OK,
        )


class ExportClinicalDataView(generics.GenericAPIView):
    """
    Exporta todos los datos clínicos del usuario en formato JSON.
    COMPLIANCE: GDPR Art. 20 (Right to Data Portability)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            profile = ClinicalProfile.objects.get(user=request.user)
        except ClinicalProfile.DoesNotExist:
            return Response(
                {"detail": "No se encontró un perfil clínico para este usuario."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir datos de exportación
        data = {
            "user": {
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email,
                "phone_number": request.user.phone_number,
            },
            "profile": {
                "dosha": profile.dosha,
                "element": profile.element,
                "diet_type": profile.diet_type,
                "sleep_quality": profile.sleep_quality,
                "activity_level": profile.activity_level,
                "medical_conditions": profile.medical_conditions,
                "allergies": profile.allergies,
                "contraindications": profile.contraindications,
                "accidents_notes": profile.accidents_notes,
                "general_notes": profile.general_notes,
            },
            "pains": [
                {
                    "body_part": pain.body_part,
                    "pain_level": pain.pain_level,
                    "periodicity": pain.periodicity,
                    "notes": pain.notes,
                    "created_at": pain.created_at.isoformat(),
                }
                for pain in profile.pains.all()
            ],
            "consents": [
                {
                    "template_version": consent.template_version,
                    "document_text": consent.document_text,
                    "is_signed": consent.is_signed,
                    "signed_at": consent.signed_at.isoformat() if consent.signed_at else None,
                    "ip_address": consent.ip_address,
                    "signature_hash": consent.signature_hash,
                    "created_at": consent.created_at.isoformat(),
                }
                for consent in profile.consents.filter(is_signed=True)
            ],
            "dosha_answers": [
                {
                    "question": answer.question.text,
                    "selected_option": answer.selected_option.text,
                    "associated_dosha": answer.selected_option.associated_dosha,
                }
                for answer in profile.dosha_answers.select_related('question', 'selected_option').all()
            ],
            "exported_at": timezone.now().isoformat(),
            "export_format_version": "1.0",
        }

        # Auditar exportación
        safe_audit_log(
            action=AuditLog.Action.ADMIN_ENDPOINT_HIT,
            admin_user=None,
            target_user=request.user,
            details={
                "action": "export_clinical_data",
                "exported_at": data["exported_at"],
                "data_categories": list(data.keys())
            }
        )

        return Response(data, status=status.HTTP_200_OK)
