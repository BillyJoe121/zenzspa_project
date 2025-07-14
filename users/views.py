from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from rest_framework import generics, status, views
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import (BlacklistedToken,
                                                             OutstandingToken)
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import CustomUser
from .permissions import IsVerified, IsAdminUser, IsStaff
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

    MAX_ATTEMPTS = 3
    LOCKOUT_PERIOD_MINUTES = 10

    def post(self, request, *args, **kwargs):
        serializer = VerifySMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']

        cache_key_attempts = f'otp_attempts_{phone_number}'
        cache_key_lockout = f'otp_lockout_{phone_number}'

        if cache.get(cache_key_lockout):
            return Response(
                {"error": f"Demasiados intentos. Por favor, intente de nuevo en {self.LOCKOUT_PERIOD_MINUTES} minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        attempts = cache.get(cache_key_attempts, 0)

        try:
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)

            if is_valid:
                cache.delete(cache_key_attempts)
                cache.delete(cache_key_lockout)

                user = CustomUser.objects.get(phone_number=phone_number)
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                return Response({"detail": "Usuario verificado correctamente."}, status=status.HTTP_200_OK)
            else:
                attempts += 1
                if attempts >= self.MAX_ATTEMPTS:
                    cache.set(cache_key_lockout, True, timedelta(minutes=self.LOCKOUT_PERIOD_MINUTES).total_seconds())
                    cache.delete(cache_key_attempts)
                else:
                    cache.set(cache_key_attempts, attempts, timeout=timedelta(minutes=self.LOCKOUT_PERIOD_MINUTES).total_seconds())

                return Response({"error": "El código de verificación es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class PasswordResetRequestView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data['phone_number']

        try:
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
            twilio_service = TwilioService()
            is_valid = twilio_service.check_verification_code(
                phone_number, code)

            if not is_valid:
                return Response({"error": "El código es inválido o ha expirado."}, status=status.HTTP_400_BAD_REQUEST)

            user = CustomUser.objects.get(phone_number=phone_number)
            user.set_password(password)
            user.save()

            return Response({"detail": "Contraseña actualizada correctamente."}, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "No se encontró un usuario con ese número de teléfono."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Ha ocurrido un error inesperado: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        new_unusable_password = CustomUser.objects.make_random_password(length=16)
        now = timezone.now()
        
        future_appointments = Appointment.objects.filter(
            user=instance,
            start_time__gte=now,
            status__in=[Appointment.AppointmentStatus.CONFIRMED,
                        Appointment.AppointmentStatus.PENDING_PAYMENT]
        )
        future_appointments.update(status=Appointment.AppointmentStatus.CANCELLED_BY_ADMIN)

        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la contraseña temporal del texto que se guarda en el log.
        AuditLog.objects.create(
            admin_user=self.request.user,
            target_user=instance,
            action=AuditLog.Action.FLAG_NON_GRATA,
            details=f"Usuario marcado como Persona Non Grata. Notas: {serializer.validated_data.get('internal_notes', 'N/A')}"
        )
        # --- FIN DE LA MODIFICACIÓN ---

        instance.is_persona_non_grata = True
        instance.is_active = False
        instance.set_password(new_unusable_password)
        
        instance.internal_notes = serializer.validated_data.get('internal_notes', instance.internal_notes)
        instance.internal_photo_url = serializer.validated_data.get('internal_photo_url', instance.internal_photo_url)

        tokens = OutstandingToken.objects.filter(user=instance)
        for token in tokens:
            try:
                BlacklistedToken.objects.get_or_create(token=token)
            except Exception:
                continue
        
        instance.save()


class StaffListView(generics.ListAPIView):
    serializer_class = StaffListSerializer
    # Ya usaba IsAuthenticated, lo cual es correcto y permite a cualquier usuario ver la lista
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # La lógica de filtrado es correcta y debe permanecer aquí.
        return CustomUser.objects.filter(role=CustomUser.Role.STAFF)