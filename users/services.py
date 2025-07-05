# Reemplaza todo el contenido de zenzspa_project/users/services.py
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


class TwilioService:
    """
    Servicio para manejar las interacciones con la API de Twilio Verify.
    """

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        if not all([self.account_sid, self.auth_token]):
            raise ValueError(
                "El SID de la cuenta y el Token de autenticación de Twilio deben estar configurados.")
        self.client = Client(self.account_sid, self.auth_token)

    def send_verification_code(self, phone_number):
        """
        Envía un código de verificación usando el servicio Twilio Verify.
        """
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        if not verify_service_sid:
            raise ValueError(
                "El SID del servicio de verificación de Twilio no está configurado.")

        try:
            verification = self.client.verify.v2.services(verify_service_sid).verifications.create(
                to=phone_number,
                channel='sms'
            )
            return verification.status
        except TwilioRestException as e:
            print(
                f"Error desde la API de Twilio al enviar código de verificación: {e}")
            raise e

    def check_verification_code(self, phone_number, code):
        """
        Verifica un código de SMS con el servicio Twilio Verify.
        """
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        if not verify_service_sid:
            raise ValueError(
                "El SID del servicio de verificación de Twilio no está configurado.")

        try:
            verification_check = self.client.verify.v2.services(verify_service_sid).verification_checks.create(
                to=phone_number,
                code=code
            )
            return verification_check.status == 'approved'
        except TwilioRestException as e:
            # Si el código es incorrecto, Twilio devuelve un 404 Not Found. Lo manejamos como un False.
            if e.status == 404:
                return False
            else:
                print(f"Error desde la API de Twilio al verificar código: {e}")
                raise e
