from django.db import transaction
from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import AuditLog
from core.utils import safe_audit_log
from users.permissions import IsAdminUser

from .models import ClinicalProfile, ClientDoshaAnswer, DoshaQuestion
from .permissions import IsVerifiedUserOrKioskSession
from .serializers import DoshaQuestionSerializer, DoshaQuizSubmissionSerializer
from .services import calculate_dominant_dosha_and_element

class DoshaQuestionViewSet(viewsets.ModelViewSet):
    queryset = DoshaQuestion.objects.all().prefetch_related('options')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsAdminUser]




class DoshaQuestionListView(generics.ListAPIView):
    """
    GET /api/v1/profiles/dosha-questions/
    Lista todas las preguntas del cuestionario Dosha con sus opciones.
    """
    queryset = DoshaQuestion.objects.filter(is_active=True).prefetch_related('options').order_by('order')
    serializer_class = DoshaQuestionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

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

