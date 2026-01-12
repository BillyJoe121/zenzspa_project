from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from spa.models import Appointment
from users.models import CustomUser
from users.permissions import IsAdminUser, IsStaffOrAdmin
from core.models import AuditLog
from core.utils import safe_audit_log

from .models import ClinicalProfile
from .permissions import ClinicalProfileAccessPermission, IsVerifiedUserOrKioskSession
from .serializers import ClinicalProfileHistorySerializer, ClinicalProfileSerializer

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
        Appointment.AppointmentStatus.CONFIRMED,
        Appointment.AppointmentStatus.FULLY_PAID,
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
        # El router puede usar 'pk' o 'phone_number' dependiendo de la configuración.
        # Intentamos obtener el valor de lookup de ambos lugares.
        phone_number = self.kwargs.get(self.lookup_url_kwarg) or self.kwargs.get('pk')
        
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

    # AÑADIR ESTE MÉTODO
    def create(self, request, *args, **kwargs):
        """
        Crear un nuevo perfil clínico para el usuario autenticado.
        Si ya existe, devuelve error 400.
        """
        # Verificar si ya existe un perfil
        if ClinicalProfile.objects.filter(user=request.user).exists():
            return Response(
                {'detail': 'El usuario ya tiene un perfil clínico.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Crear el perfil con valores por defecto
        # Use defaults compatible with the model.
        # Assuming defaults are empty strings as per user instruction.
        profile = ClinicalProfile.objects.create(
            user=request.user,
            dosha='UNKNOWN',
            element='',
            diet_type='',
            sleep_quality='',
            activity_level='',
            medical_conditions='',
            allergies='',
            contraindications='',
            accidents_notes='',
            general_notes=''
        )
        serializer = self.get_serializer(profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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


