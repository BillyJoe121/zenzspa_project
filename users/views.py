# Reemplaza todo el contenido de zenzspa_project/users/views.py
from django.db import transaction
from django.utils import timezone  # <- IMPORTACIÓN AÑADIDA
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import (BlacklistedToken,
                                                             OutstandingToken)
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import CustomUser
from .serializers import (CustomTokenObtainPairSerializer,
                          FlagNonGrataSerializer,
                          PasswordResetConfirmSerializer,
                          PasswordResetRequestSerializer, SimpleUserSerializer,
                          UserRegistrationSerializer, VerifySMSSerializer, StaffListSerializer)
from .services import TwilioService
from spa.models import Appointment
from core.models import AuditLog


class UserRegistrationView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        try:
            twilio_service = TwilioService()
            twilio_service.send_verification_code(user.phone_number)
        except Exception as e:
            print(
                f"Error enviando SMS de verificación al usuario {user.phone_number}: {e}")


class VerifySMSView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = VerifySMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)
            if is_valid:
                user = CustomUser.objects.get(phone_number=phone_number)
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                return Response({"detail": "Usuario verificado correctamente."}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "El código de verificación es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# --- VISTAS DE RESETEO DE CONTRASEÑA (VERSIÓN CON TWILIO VERIFY) ---

class PasswordResetRequestView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']

        try:
            # Reutilizamos el servicio de verificación existente
            twilio_service = TwilioService()
            twilio_service.send_verification_code(phone_number)
        except Exception as e:
            print(
                f"Error al enviar SMS de reseteo (vía Verify) a {phone_number}: {e}")

        return Response(
            {"detail": "Si existe una cuenta asociada a este número, recibirás un código de verificación."},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        password = serializer.validated_data['password']

        try:
            # Reutilizamos la comprobación del servicio de verificación
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)

            if not is_valid:
                return Response({"error": "El código es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.get(phone_number=phone_number)
            user.set_password(password)
            user.save()

            # Twilio Verify maneja el código, no hay nada que borrar de la caché.
            return Response({"detail": "Contraseña actualizada correctamente."}, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- VISTAS AUXILIARES ---

class CurrentUserView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SimpleUserSerializer

    def get_object(self):
        return self.request.user


class FlagNonGrataView(generics.UpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = FlagNonGrataSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'phone_number'

    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()

        # --- INICIO DE CAMBIOS QUIRÚRGICOS ---

        # 1. Generar una contraseña aleatoria y segura ANTES de hacer otras operaciones
        new_unusable_password = CustomUser.objects.make_random_password(
            length=16)

        # --- FIN DE CAMBIOS QUIRÚRGICOS ---

        # Cancelar citas futuras
        now = timezone.now()
        future_appointments = Appointment.objects.filter(
            user=instance,
            start_time__gte=now,
            # Aseguramos que el status sea correcto, usando el Enum del modelo Appointment
            status__in=[Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT]
        )
        # Cambiamos el status al correcto según el modelo
        future_appointments.update(
            status=Appointment.AppointmentStatus.CANCELLED_BY_ADMIN)

        # Crear el registro de auditoría
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=instance,
            action=AuditLog.Action.FLAG_NON_GRATA,
            # 2. Modificamos los detalles para incluir la nueva contraseña
            details=f"Notas: {serializer.validated_data.get('internal_notes', 'N/A')}\n"
            f"New Unusable Password: {new_unusable_password}"
        )

        # Actualizar la instancia del usuario
        instance.is_persona_non_grata = True
        instance.is_active = False  # Es buena práctica desactivar al usuario también
        # 3. Usamos la nueva contraseña aleatoria en lugar de None
        instance.set_password(new_unusable_password)

        # Invalidar tokens
        tokens = OutstandingToken.objects.filter(user=instance)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                # Si el token ya está en la lista negra, no hacemos nada
                continue

        # El serializer.save() se encarga de guardar los campos del serializador
        # como 'internal_notes'. Los otros cambios los guardamos manualmente.
        instance.save()


class StaffListView(generics.ListAPIView):
    """
    Vista de solo lectura para listar todos los usuarios con el rol 'STAFF'.
    Accesible por cualquier usuario autenticado.
    """
    serializer_class = StaffListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Sobrescribimos este método para devolver solo los usuarios que son STAFF.
        """
        return CustomUser.objects.filter(role=CustomUser.Role.STAFF)
