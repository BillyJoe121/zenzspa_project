"""
Vista de webhook para mensajes de WhatsApp vía Twilio.
"""
import html
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ...models import AnonymousUser
from ...throttling import BotDailyThrottle, BotIPThrottle, BotRateThrottle
from .utils import get_client_ip

logger = logging.getLogger(__name__)


class WhatsAppWebhookView(APIView):
    """
    Webhook para recibir mensajes entrantes de Twilio WhatsApp.

    POST /api/v1/bot/whatsapp/
    Content-Type: application/x-www-form-urlencoded

    Twilio envía:
    - Body: Texto del mensaje
    - From: Número de teléfono del remitente (whatsapp:+573157589548)
    - To: Número de tu negocio
    - MessageSid: ID del mensaje
    - X-Twilio-Signature: Firma para validación (opcional)

    Responde con TwiML:
    <?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>Respuesta del bot</Message>
    </Response>
    """
    permission_classes = [AllowAny]
    throttle_classes = [BotRateThrottle, BotDailyThrottle, BotIPThrottle]

    def _validate_twilio_signature(self, request):
        """
        Valida la firma de Twilio para asegurar que el request viene de Twilio.
        Opcional pero recomendado para producción.

        Returns:
            bool: True si la firma es válida o si la validación está desactivada
        """
        # Solo validar si está configurado
        if not getattr(settings, 'VALIDATE_TWILIO_SIGNATURE', False):
            return True

        try:
            from twilio.request_validator import RequestValidator

            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            if not auth_token:
                logger.warning("TWILIO_AUTH_TOKEN no configurado, saltando validación de firma")
                return True

            validator = RequestValidator(auth_token)

            # Obtener URL completa del request
            url = request.build_absolute_uri()

            # Obtener firma del header
            signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

            # Obtener parámetros POST
            params = request.POST.dict()

            # Validar
            is_valid = validator.validate(url, params, signature)

            if not is_valid:
                logger.warning("Firma de Twilio inválida. URL: %s", url)

            return is_valid

        except ImportError:
            logger.warning("twilio package no instalado, saltando validación de firma")
            return True
        except Exception as e:
            logger.error("Error validando firma de Twilio: %s", e)
            return False

    def _normalize_phone_number(self, whatsapp_number: str) -> str:
        """
        Normaliza número de WhatsApp a formato E.164.

        Input: whatsapp:+573157589548
        Output: +573157589548
        """
        if whatsapp_number.startswith('whatsapp:'):
            return whatsapp_number[9:]  # Remover prefijo 'whatsapp:'
        return whatsapp_number

    def _get_user_from_phone(self, phone_number: str):
        """
        Busca usuario por número de teléfono.

        Returns:
            tuple: (user, anonymous_user, user_id_for_security)
        """
        from users.models import CustomUser

        # Intentar encontrar usuario registrado
        user = CustomUser.objects.filter(
            phone_number=phone_number,
            is_active=True
        ).first()

        if user:
            return user, None, str(user.id)

        # Usuario no registrado, crear anónimo temporal
        # Usamos el número de teléfono como identificador único
        client_ip = '0.0.0.0'  # Twilio no pasa IP del cliente

        # Buscar si ya existe un usuario anónimo con este teléfono en metadata
        anonymous_user = AnonymousUser.objects.filter(
            metadata__phone_number=phone_number
        ).first()

        if not anonymous_user or anonymous_user.is_expired:
            # Crear nuevo usuario anónimo
            anonymous_user = AnonymousUser.objects.create(
                ip_address=client_ip,
                metadata={'phone_number': phone_number, 'channel': 'whatsapp'}
            )
            logger.info("Nuevo usuario anónimo WhatsApp creado: %s", phone_number)

        return None, anonymous_user, f"whatsapp_{phone_number}"

    def _get_last_notification(self, user, phone_number: str):
        """
        Obtiene la última notificación enviada al usuario por WhatsApp.

        Returns:
            dict o None
        """
        from notifications.models import NotificationLog, NotificationTemplate

        # Buscar última notificación
        if user:
            last_log = NotificationLog.objects.filter(
                user=user,
                channel=NotificationTemplate.ChannelChoices.WHATSAPP,
                status=NotificationLog.Status.SENT
            ).order_by('-created_at').first()
        else:
            # Para usuarios anónimos, buscar por teléfono en metadata
            last_log = NotificationLog.objects.filter(
                metadata__phone_number=phone_number,
                channel=NotificationTemplate.ChannelChoices.WHATSAPP,
                status=NotificationLog.Status.SENT
            ).order_by('-created_at').first()

        if not last_log:
            return None

        # Construir diccionario con info relevante
        payload = last_log.payload or {}
        return {
            'event_code': last_log.event_code,
            'subject': payload.get('subject', ''),
            'body': payload.get('body', ''),
            'sent_at': last_log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'channel': 'WhatsApp',
            'metadata': last_log.metadata or {}
        }

    def _generate_twiml_response(self, message_text: str) -> str:
        """
        Genera respuesta en formato TwiML para Twilio.

        Args:
            message_text: Texto de la respuesta del bot

        Returns:
            str: XML TwiML
        """
        # Escapar caracteres especiales XML
        escaped_text = html.escape(message_text)

        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{escaped_text}</Message>
</Response>'''

        return twiml

    def post(self, request):
        """
        Procesa mensaje entrante de WhatsApp vía Twilio.
        """
        # 1. Validar firma de Twilio (opcional pero recomendado)
        if not self._validate_twilio_signature(request):
            logger.warning("Firma de Twilio inválida rechazada")
            return Response(
                self._generate_twiml_response("Error de autenticación."),
                content_type='application/xml',
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Extraer datos del formulario de Twilio
        try:
            body = request.POST.get('Body', '').strip()
            from_number = request.POST.get('From', '')
            message_sid = request.POST.get('MessageSid', '')

            logger.info("WhatsApp webhook recibido. From: %s, MessageSid: %s", from_number, message_sid)

            # 3. Validar que tengamos mensaje
            if not body:
                return Response(
                    self._generate_twiml_response("No recibí ningún mensaje. ¿Puedes escribir algo?"),
                    content_type='application/xml'
                )

            # 4. Normalizar número de teléfono
            phone_number = self._normalize_phone_number(from_number)

            # 5. Obtener o crear usuario
            user, anonymous_user, user_id_for_security = self._get_user_from_phone(phone_number)

            # 6. Obtener última notificación (contexto adicional)
            last_notification = self._get_last_notification(user, phone_number)
            extra_context = None
            if last_notification:
                extra_context = {"last_notification": last_notification}

            # 7. Obtener IP del cliente
            client_ip = get_client_ip(request)

            # 8. Procesar mensaje con la lógica compartida
            from ...services.shared import process_bot_message

            response_data = process_bot_message(
                user=user,
                anonymous_user=anonymous_user,
                user_message=body,
                client_ip=client_ip,
                user_id_for_security=user_id_for_security,
                extra_context=extra_context
            )

            reply_text = response_data.get('reply', 'Lo siento, hubo un error procesando tu mensaje.')

            logger.info(
                "WhatsApp respuesta enviada. To: %s, MessageSid: %s",
                phone_number, message_sid
            )

        except PermissionError as e:
            # Usuario bloqueado o límite excedido
            reply_text = str(e)
            logger.warning("WhatsApp mensaje bloqueado: %s", e)

        except ValueError as e:
            # Error de validación
            reply_text = f"Error: {str(e)}"
            logger.warning("WhatsApp validación fallida: %s", e)

        except RuntimeError as e:
            # Error del sistema
            reply_text = "El servicio está temporalmente no disponible. Por favor intenta más tarde."
            logger.error("WhatsApp error del sistema: %s", e)

        except Exception as e:
            # Error inesperado
            reply_text = "Ocurrió un error inesperado. Por favor intenta de nuevo."
            logger.exception("WhatsApp error inesperado: %s", e)

        # 9. Generar y devolver TwiML
        twiml_response = self._generate_twiml_response(reply_text)

        return Response(
            twiml_response,
            content_type='application/xml',
            status=status.HTTP_200_OK
        )
