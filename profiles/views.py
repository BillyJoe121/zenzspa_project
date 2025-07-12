from rest_framework import generics, viewsets, status
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
from .permissions import IsOwnerForReadOrStaff, IsKioskSession, IsStaffOrAdmin
from users.models import CustomUser
from users.permissions import IsAdminUser, IsVerified
from .services import calculate_dominant_dosha_and_element
from rest_framework.permissions import IsAuthenticated

class ClinicalProfileDetailView(generics.RetrieveUpdateAPIView):
    """
    Vista para ver y actualizar el perfil clínico de un usuario.
    - El dueño puede ver su perfil.
    - El personal (STAFF/ADMIN) puede ver y actualizar cualquier perfil.
    """
    queryset = ClinicalProfile.objects.all().select_related('user').prefetch_related('pains')
    serializer_class = ClinicalProfileSerializer
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se reemplaza el permiso anterior por el nuevo permiso granular.
    # IsAuthenticated se asegura que solo usuarios logueados puedan intentarlo.
    permission_classes = [IsAuthenticated, IsOwnerForReadOrStaff]
    # --- FIN DE LA MODIFICACIÓN ---
    lookup_field = 'user__phone_number'
    lookup_url_kwarg = 'phone_number'

    def get_object(self):
        phone_number = self.kwargs[self.lookup_url_kwarg]
        user = get_object_or_404(CustomUser, phone_number=phone_number)
        # La comprobación de permisos se hará después de obtener el objeto.
        obj = get_object_or_404(ClinicalProfile, user=user)
        self.check_object_permissions(self.request, obj)
        return obj


class DoshaQuestionViewSet(viewsets.ModelViewSet):
    queryset = DoshaQuestion.objects.all().prefetch_related('options')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsAdminUser]


class DoshaQuestionListView(generics.ListAPIView):
    queryset = DoshaQuestion.objects.all().prefetch_related('options').order_by('category', 'created_at')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsVerified]


class DoshaQuizSubmitView(generics.GenericAPIView):
    serializer_class = DoshaQuizSubmissionSerializer
    permission_classes = [IsVerified]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        answers_data = serializer.validated_data.get('answers', [])
        profile = request.user.profile

        with transaction.atomic():
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

        result = calculate_dominant_dosha_and_element(profile.id)

        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)
    
class KioskStartSessionView(generics.GenericAPIView):
    """
    Vista para que un STAFF inicie una sesión de Modo Quiosco para un cliente.
    """
    serializer_class = KioskStartSessionSerializer
    permission_classes = [IsStaffOrAdmin] # Solo el personal puede iniciar el quiosco

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
