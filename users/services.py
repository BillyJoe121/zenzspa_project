# Reemplaza todo el contenido de studiozens_project/users/services.py
import logging
import time
from typing import Optional

import requests
from django.conf import settings
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from core.exceptions import BusinessLogicError

logger = logging.getLogger(__name__)

# Imports for TOTP
import hmac
import struct
import hashlib
import base64
import os



class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open."""


class SimpleCircuitBreaker:
    """
    Minimal circuit breaker to prevent cascading failures when Twilio is unavailable.
    """

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.opened_at = None

    def _is_open(self):
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at > self.recovery_timeout:
            # Half-open: allow new attempt and reset counters
            self.failures = 0
            self.opened_at = None
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.opened_at = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()

    def call(self, func, *args, **kwargs):
        if self._is_open():
            raise CircuitBreakerOpen()
        try:
            result = func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result


twilio_breaker = SimpleCircuitBreaker(
    failure_threshold=getattr(settings, "TWILIO_CB_FAILURES", 5),
    recovery_timeout=getattr(settings, "TWILIO_CB_TIMEOUT", 60),
)


class TwilioService:
    """
    Servicio para manejar las interacciones con la API de Twilio Verify.
    """

    REQUEST_TIMEOUT = getattr(settings, "TWILIO_TIMEOUT", 10)

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        if not all([self.account_sid, self.auth_token]):
            raise ValueError(
                "El SID de la cuenta y el Token de autenticación de Twilio deben estar configurados.")
        self.client = Client(self.account_sid, self.auth_token)

    def _call_with_breaker(self, func):
        try:
            return twilio_breaker.call(func)
        except CircuitBreakerOpen:
            logger.error("Circuit breaker abierto para Twilio.")
            raise BusinessLogicError(
                detail="Servicio de verificación no disponible temporalmente.",
                internal_code="USER-TWILIO-BLOCKED",
            )

    def send_verification_code(self, phone_number):
        """
        Envía un código de verificación usando el servicio Twilio Verify.
        Incluye timeout explícito para prevenir bloqueos indefinidos.
        """
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        if not verify_service_sid:
            raise ValueError(
                "El SID del servicio de verificación de Twilio no está configurado.")

        def _perform():
            # Timeout explícito configurado en el cliente HTTP de Twilio
            verification = self.client.verify.v2.services(verify_service_sid).verifications.create(
                to=phone_number,
                channel='sms'
            )
            logger.info("OTP sent via Twilio", extra={"phone": phone_number[-4:], "context": "send_verification"})
            return verification.status

        try:
            return self._call_with_breaker(_perform)
        except TwilioRestException as e:
            logger.error("Error desde la API de Twilio al enviar código de verificación: %s", e)
            raise BusinessLogicError(
                detail="Error al enviar código de verificación. Intenta más tarde.",
                internal_code="USER-TWILIO-ERROR",
            )
        except BusinessLogicError:
            raise
        except Exception as exc:
            logger.exception("Error inesperado enviando OTP: %s", exc, extra={"phone": phone_number[-4:]})
            raise BusinessLogicError(
                detail="Servicio de verificación no disponible.",
                internal_code="USER-TWILIO-UNAVAILABLE",
            )

    def check_verification_code(self, phone_number, code):
        """
        Verifica un código de SMS con el servicio Twilio Verify.
        Incluye timeout explícito para prevenir bloqueos indefinidos.
        """
        verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        if not verify_service_sid:
            raise ValueError(
                "El SID del servicio de verificación de Twilio no está configurado.")

        def _perform():
            # Timeout explícito configurado en el cliente HTTP de Twilio
            verification_check = self.client.verify.v2.services(verify_service_sid).verification_checks.create(
                to=phone_number,
                code=code
            )
            logger.info("OTP verification checked", extra={"phone": phone_number[-4:], "context": "check_verification"})
            return verification_check.status == 'approved'

        try:
            return self._call_with_breaker(_perform)
        except TwilioRestException as e:
            if e.status == 404:
                return False
            logger.error("Error verificando código OTP en Twilio: %s", e)
            raise BusinessLogicError(
                detail="Error al verificar código de verificación.",
                internal_code="USER-TWILIO-ERROR",
            )
        except BusinessLogicError:
            raise
        except Exception as exc:
            logger.exception("Error inesperado verificando OTP: %s", exc, extra={"phone": phone_number[-4:]})
            raise BusinessLogicError(
                detail="Servicio de verificación no disponible.",
                internal_code="USER-TWILIO-UNAVAILABLE",
            )


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


class TOTPService:
    """
    Servicio para manejar 2FA con aplicaciones (Google Authenticator, etc.)
    Implementación básica de RFC 6238 (TOTP) para evitar dependencias externas si no están disponibles.
    """
    @staticmethod
    def generate_secret():
        return base64.b32encode(os.urandom(20)).decode('utf-8')

    @staticmethod
    def get_totp_token(secret, interval=30):
        if not secret:
            return None
        try:
            key = base64.b32decode(secret, casefold=True)
        except Exception:
            return None
        msg = struct.pack(">Q", int(time.time()) // interval)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[19] & 15
        h = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
        return str(h).zfill(6)

    @staticmethod
    def verify_token(secret, token, window=1):
        """
        Verifica el token TOTP permitiendo una ventana de tiempo (window * 30s) hacia atrás y adelante.
        """
        if not secret or not token:
            return False
        
        try:
            key = base64.b32decode(secret, casefold=True)
        except Exception:
            return False

        current_ts = int(time.time()) // 30
        for i in range(-window, window + 1):
            ts = current_ts + i
            msg = struct.pack(">Q", ts)
            h = hmac.new(key, msg, hashlib.sha1).digest()
            o = h[19] & 15
            h_val = (struct.unpack(">I", h[o:o+4])[0] & 0x7fffffff) % 1000000
            if str(h_val).zfill(6) == str(token):
                return True
        return False

    @staticmethod
    def get_provisioning_uri(user, secret, issuer_name="StudioZens"):
        return f"otpauth://totp/{issuer_name}:{user.email or user.phone_number}?secret={secret}&issuer={issuer_name}"


class GeoIPService:
    """
    Servicio para Geolocalización usando GeoIP2.
    """
    _reader = None

    @classmethod
    def _get_reader(cls):
        if cls._reader is None:
            try:
                import geoip2.database
                db_path = getattr(settings, 'GEOIP_PATH', None)
                if db_path and os.path.exists(db_path):
                    cls._reader = geoip2.database.Reader(db_path)
            except ImportError:
                logger.warning("geoip2 library not installed.")
            except Exception as e:
                logger.warning(f"Error initializing GeoIP2 reader: {e}")
        return cls._reader

    @staticmethod
    def get_country_from_ip(ip_address):
        # Localhost checks
        if ip_address in ['127.0.0.1', '::1']:
            return 'CO'
        
        reader = GeoIPService._get_reader()
        if reader:
            try:
                response = reader.country(ip_address)
                return response.country.iso_code or 'CO'
            except Exception as e:
                logger.warning(f"GeoIP lookup failed for {ip_address}: {e}")
        
        return 'CO'  # Default seguro

    @staticmethod
    def is_ip_allowed(ip_address, allowed_countries=None):
        if allowed_countries is None:
            allowed_countries = ['CO'] # Default Colombia
        country = GeoIPService.get_country_from_ip(ip_address)
        return country in allowed_countries

