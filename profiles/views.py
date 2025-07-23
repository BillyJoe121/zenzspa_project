from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.core.cache import cache
import secrets
from datetime import timedelta
from .models import ClinicalProfile, DoshaQuestion, ClientDoshaAnswer
from .serializers import (
    ClinicalProfileSerializer, DoshaQuestionSerializer,
    DoshaQuizSubmissionSerializer, KioskStartSessionSerializer
)
from users.models import CustomUser
from .services import calculate_dominant_dosha_and_element
from users.permissions import IsAdminUser, IsVerified, IsStaffOrAdmin
from .permissions import ClinicalProfileAccessPermission, IsKioskSession, IsVerifiedUserOrKioskSession 
from rest_framework.permissions import IsAuthenticated

class ClinicalProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar Perfiles Clínicos (CRUD completo).
    Utiliza 'ClinicalProfileAccessPermission' para cumplir con RFD-CLI-02.
    """
    queryset = ClinicalProfile.objects.select_related('user').prefetch_related('pains', 'dosha_answers')
    serializer_class = ClinicalProfileSerializer
    permission_classes = [IsAuthenticated, ClinicalProfileAccessPermission]
    
    lookup_field = 'user__phone_number'
    lookup_url_kwarg = 'phone_number'

    def get_object(self):
        phone_number = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset()
        filter_kwargs = {self.lookup_field: phone_number}
        obj = get_object_or_404(queryset, **filter_kwargs)
        return obj

    # Se añade una acción personalizada para el endpoint /me/
    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request, *args, **kwargs):
        """
        Endpoint para que el usuario autenticado vea o actualice su propio perfil.
        """
        # Obtenemos el perfil del usuario que hace la petición
        profile = get_object_or_404(ClinicalProfile, user=request.user)
        
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
        kiosk_token = request.headers.get('X-Kiosk-Token')
        if kiosk_token:
            cache.delete(f"kiosk_session_{kiosk_token}")

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
        staff_member = request.user

        # Generar un token seguro y temporal
        kiosk_token = secrets.token_hex(20)
        
        # Guardar la información de la sesión en la caché de Redis por 30 minutos
        session_data = {'client_id': str(client.id), 'staff_id': str(staff_member.id)}
        cache.set(f"kiosk_session_{kiosk_token}", session_data, timeout=timedelta(minutes=30).total_seconds())

        return Response({'kiosk_token': kiosk_token}, status=status.HTTP_200_OK)
