# Reemplaza todo el contenido de zenzspa_project/users/services.py
import logging
from typing import Optional

import requests
from django.conf import settings
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logger = logging.getLogger(__name__)


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


def _resolve_recaptcha_secret():
    return getattr(settings, "RECAPTCHA_V3_SECRET_KEY", None) or getattr(settings, "RECAPTCHA_SECRET_KEY", None)


def _resolve_threshold(action: Optional[str], explicit: Optional[float]) -> float:
    if explicit is not None:
        return explicit
    action_scores = getattr(settings, "RECAPTCHA_V3_ACTION_SCORES", {}) or {}
    if action and action in action_scores:
        return action_scores[action]
    return getattr(settings, "RECAPTCHA_V3_DEFAULT_SCORE", 0.5)


def verify_recaptcha(token, remote_ip=None, action=None, min_score=None):
    secret = _resolve_recaptcha_secret()
    if not secret or not token:
        logger.warning("No se puede verificar reCAPTCHA: faltan credenciales o token.")
        return False

    payload = {
        "secret": secret,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        response = requests.post("https://www.google.com/recaptcha/api/siteverify", data=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error("Error verificando reCAPTCHA: %s", exc)
        return False

    if not data.get("success"):
        logger.warning("reCAPTCHA falló: %s", data.get("error-codes"))
        return False

    expected_action = action
    received_action = data.get("action")
    if expected_action and received_action and expected_action != received_action:
        logger.warning("Acción reCAPTCHA inesperada. Esperado=%s recibido=%s", expected_action, received_action)
        return False

    score = data.get("score")
    threshold = _resolve_threshold(expected_action, min_score)
    if score is None:
        # Al no tener score, asumimos v2 y aceptamos la validación exitosa
        return True
    if score < threshold:
        logger.info("reCAPTCHA score %s por debajo del umbral %s para acción %s", score, threshold, expected_action)
        return False
    return True
