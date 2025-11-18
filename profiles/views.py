from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClinicalProfile, ConsentTemplate, DoshaQuestion, ClientDoshaAnswer, KioskSession
from .permissions import (
    ClinicalProfileAccessPermission,
    IsKioskSession,
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

class ClinicalProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar Perfiles Clínicos (CRUD completo).
    Utiliza 'ClinicalProfileAccessPermission' para cumplir con RFD-CLI-02.
    """
    queryset = ClinicalProfile.objects.select_related('user').prefetch_related('pains', 'dosha_answers')
    serializer_class = ClinicalProfileSerializer
    permission_classes = [IsVerifiedUserOrKioskSession, ClinicalProfileAccessPermission]
    
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
        if user.role in [CustomUser.Role.ADMIN, CustomUser.Role.STAFF]:
            return base_queryset
        return base_queryset.filter(user=user)

    def get_object(self):
        phone_number = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset()
        filter_kwargs = {self.lookup_field: phone_number}
        obj = get_object_or_404(queryset, **filter_kwargs)
        kiosk_client = getattr(self.request, 'kiosk_client', None)
        if kiosk_client and obj.user != kiosk_client:
            raise PermissionDenied("La sesión de quiosco no puede acceder a este perfil.")
        return obj

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
            kiosk_session.deactivate()

        return Response(result, status=status.HTTP_200_OK)

class KioskStartSessionView(generics.GenericAPIView):
    """
    Vista para que un STAFF inicie una sesión de Modo Quiosco para un cliente.
    """
    serializer_class = KioskStartSessionSerializer
    permission_classes = [IsStaffOrAdmin]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        client_phone = serializer.validated_data['client_phone_number']
        client = CustomUser.objects.get(phone_number=client_phone)
        profile, _ = ClinicalProfile.objects.get_or_create(user=client)
        staff_member = request.user

        timeout_minutes = getattr(settings, "KIOSK_SESSION_TIMEOUT_MINUTES", 5)
        expires_at = timezone.now() + timedelta(minutes=timeout_minutes)
        session = KioskSession.objects.create(
            profile=profile,
            staff_member=staff_member,
            expires_at=expires_at,
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
    permission_classes = []
    serializer_class = KioskSessionStatusSerializer

    def get(self, request, *args, **kwargs):
        session = load_kiosk_session_from_request(request, allow_inactive=True)
        if not session:
            return Response({'detail': 'Sesión de quiosco no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
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
        return Response(
            {
                "detail": "Sesión bloqueada.",
                "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
                "status": session.status,
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionDiscardChangesView(generics.GenericAPIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        session = load_kiosk_session_from_request(request, allow_inactive=True)
        if not session:
            return Response({'detail': 'Sesión de quiosco no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        session.lock()
        session.clear_pending_changes()
        return Response(
            {
                "detail": "Cambios descartados y sesión finalizada.",
                "status": session.status,
                "secure_screen_url": getattr(settings, "KIOSK_SECURE_SCREEN_URL", "/kiosk/secure"),
            },
            status=status.HTTP_200_OK,
        )


class KioskSessionSecureScreenView(generics.GenericAPIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        session = load_kiosk_session_from_request(request, allow_inactive=True)
        if not session:
            return Response({'detail': 'Sesión de quiosco no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        session.lock()
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
        return Response({"has_pending_changes": True}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        session = request.kiosk_session
        session.clear_pending_changes()
        return Response({"has_pending_changes": False}, status=status.HTTP_200_OK)


class ClinicalProfileHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provee acceso de solo lectura al historial versionado de los perfiles.
    """

    permission_classes = [IsAuthenticated, IsStaffOrAdmin]
    serializer_class = ClinicalProfileHistorySerializer

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
