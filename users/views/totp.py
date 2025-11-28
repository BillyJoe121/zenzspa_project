"""
Vistas para autenticación de dos factores (2FA/TOTP).
"""
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..serializers import TOTPSetupSerializer, TOTPVerifySerializer
from ..services import TOTPService


class TOTPSetupView(views.APIView):
    """Configura 2FA para el usuario."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        secret = TOTPService.generate_secret()
        user.totp_secret = secret
        user.save(update_fields=['totp_secret'])

        uri = TOTPService.get_provisioning_uri(user, secret)
        serializer = TOTPSetupSerializer({"secret": secret, "provisioning_uri": uri})
        return Response(serializer.data)


class TOTPVerifyView(views.APIView):
    """Verifica código TOTP del usuario."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']
        user = request.user

        if not user.totp_secret:
            return Response({"error": "2FA no configurado."}, status=status.HTTP_400_BAD_REQUEST)

        if TOTPService.verify_token(user.totp_secret, token):
            return Response({"detail": "Código verificado correctamente. 2FA activado."}, status=status.HTTP_200_OK)

        return Response({"error": "Código inválido."}, status=status.HTTP_400_BAD_REQUEST)
