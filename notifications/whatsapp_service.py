"""
Servicio centralizado para envío de WhatsApp vía Twilio.
Usado por NotificationService como un canal más.
Soporta templates aprobados por Meta y mensajes dinámicos.
"""
import logging
from django.conf import settings
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Servicio centralizado para envío de WhatsApp vía Twilio.
    Soporta 2 modos:
    1. Templates aprobados (content_sid + variables)
    2. Mensajes dinámicos (free-form body) - solo dentro de ventana 24h
    """

    @staticmethod
    def send_template_message(
        to_phone: str,
        content_sid: str,
        content_variables: Dict[str, str],
        media_url: Optional[str] = None
    ) -> dict:
        """
        Envía mensaje usando template aprobado por Meta.

        Args:
            to_phone: Número destino en formato E.164 (+573001234567)
            content_sid: Content SID del template aprobado (HXxxxx...)
            content_variables: Dict con variables del template {"1": "value", "2": "value"}
            media_url: URL de imagen (opcional, sobrescribe la del template)

        Returns:
            dict con {success: bool, sid: str, error: str}
        """
        if not WhatsAppService._verify_credentials():
            return {
                "success": False,
                "error": "Credenciales Twilio faltantes"
            }

        try:
            from twilio.rest import Client

            client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )

            from_whatsapp = f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
            to_whatsapp = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

            # Construir parámetros del mensaje
            message_params = {
                "from_": from_whatsapp,
                "to": to_whatsapp,
                "content_sid": content_sid,
                "content_variables": content_variables,
            }

            # Agregar media_url si se proporciona (sobrescribe la del template)
            if media_url:
                message_params["media_url"] = [media_url]

            message = client.messages.create(**message_params)

            logger.info(
                "WhatsApp template enviado a %s: SID=%s, ContentSID=%s",
                WhatsAppService._mask_phone(to_phone),
                message.sid,
                content_sid
            )

            return {
                "success": True,
                "sid": message.sid,
                "error": None
            }

        except ImportError:
            logger.error("Módulo twilio no instalado. Ejecutar: pip install twilio")
            return {
                "success": False,
                "error": "Módulo twilio no instalado"
            }

        except Exception as e:
            logger.error(
                "Error enviando WhatsApp template a %s: %s",
                WhatsAppService._mask_phone(to_phone),
                str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def send_message(to_phone: str, body: str) -> dict:
        """
        Envía mensaje WhatsApp dinámico (free-form).
        SOLO funciona dentro de ventana de 24h después que el usuario escriba.

        Args:
            to_phone: Número destino en formato E.164 (+573001234567)
            body: Cuerpo del mensaje (máx 1600 caracteres)

        Returns:
            dict con {success: bool, sid: str, error: str}
        """
        if not WhatsAppService._verify_credentials():
            return {
                "success": False,
                "error": "Credenciales Twilio faltantes"
            }

        try:
            from twilio.rest import Client

            client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )

            # Twilio requiere "whatsapp:" prefix
            from_whatsapp = f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
            to_whatsapp = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

            # Truncar mensaje si excede límite
            body_truncated = body[:1600]
            if len(body) > 1600:
                body_truncated = body[:1597] + "..."
                logger.warning(
                    "Mensaje WhatsApp truncado de %d a 1600 caracteres",
                    len(body)
                )

            message = client.messages.create(
                body=body_truncated,
                from_=from_whatsapp,
                to=to_whatsapp
            )

            logger.info(
                "WhatsApp enviado a %s: SID=%s",
                WhatsAppService._mask_phone(to_phone),
                message.sid
            )

            return {
                "success": True,
                "sid": message.sid,
                "error": None
            }

        except ImportError:
            logger.error("Módulo twilio no instalado. Ejecutar: pip install twilio")
            return {
                "success": False,
                "error": "Módulo twilio no instalado"
            }

        except Exception as e:
            logger.error(
                "Error enviando WhatsApp a %s: %s",
                WhatsAppService._mask_phone(to_phone),
                str(e)
            )
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def _verify_credentials() -> bool:
        """Verifica que las credenciales Twilio estén configuradas"""
        if not all([
            getattr(settings, 'TWILIO_ACCOUNT_SID', None),
            getattr(settings, 'TWILIO_AUTH_TOKEN', None),
            getattr(settings, 'TWILIO_WHATSAPP_FROM', None)
        ]):
            logger.error("Credenciales Twilio WhatsApp no configuradas")
            return False
        return True

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """Enmascara número para logs"""
        if not phone or len(phone) < 8:
            return "***"
        return f"{phone[:3]}***{phone[-2:]}"

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """
        Valida formato de teléfono para WhatsApp.
        Debe estar en formato E.164: +573001234567
        """
        if not phone:
            return False

        # Remover espacios/guiones
        clean_phone = phone.replace(" ", "").replace("-", "")

        # Debe empezar con + y tener 10-15 dígitos
        if not clean_phone.startswith("+"):
            return False

        digits = clean_phone[1:]
        if not digits.isdigit():
            return False

        if len(digits) < 10 or len(digits) > 15:
            return False

        return True
