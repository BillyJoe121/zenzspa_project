"""
Tests para el webhook de WhatsApp (Twilio).
"""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework.test import APIClient
from model_bakery import baker


@pytest.mark.django_db
class TestWhatsAppWebhook:
    """Tests para WhatsAppWebhookView"""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('whatsapp-webhook')
        self.valid_data = {
            'Body': 'Hola, necesito información',
            'From': 'whatsapp:+573157589548',
            'MessageSid': 'SM1234567890abcdef',
        }

    def test_webhook_url_exists(self):
        """Verifica que la URL del webhook exista"""
        response = self.client.post(self.url, data={})
        # No debe ser 404
        assert response.status_code != 404

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_whatsapp_message_creates_anonymous_user(self, mock_get_user, mock_process):
        """Verifica que un mensaje de WhatsApp crea un usuario anónimo"""
        from bot.models import AnonymousUser

        # Crear un usuario anónimo mock
        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0', phone_number='+573157589548')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.return_value = {'reply': 'Hola, ¿en qué puedo ayudarte?'}

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        # The response is XML, not JSON-escaped
        content = response.content.decode('utf-8')
        assert '<?xml version=' in content
        assert '<Response>' in content
        assert '<Message>' in content

    @patch('bot.services_shared.process_bot_message')
    def test_whatsapp_registered_user(self, mock_process):
        """Verifica que un usuario registrado se detecta correctamente"""
        from users.models import CustomUser

        # Crear usuario registrado con el mismo teléfono
        user = baker.make(
            CustomUser,
            phone_number='+573157589548',
            is_active=True
        )

        mock_process.return_value = {'reply': 'Hola de nuevo!'}

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        # Verificar que process_bot_message fue llamado con el usuario correcto
        assert mock_process.called
        call_args = mock_process.call_args[1]
        assert call_args['user'] == user
        assert call_args['anonymous_user'] is None

    def test_empty_message_returns_prompt(self):
        """Verifica que un mensaje vacío retorna un mensaje de prompt"""
        data = self.valid_data.copy()
        data['Body'] = ''

        response = self.client.post(self.url, data=data)

        assert response.status_code == 200
        assert b'No recib' in response.content  # "No recibí ningún mensaje"

    def test_missing_body_returns_prompt(self):
        """Verifica que la ausencia de Body retorna un mensaje de prompt"""
        data = self.valid_data.copy()
        del data['Body']

        response = self.client.post(self.url, data=data)

        assert response.status_code == 200
        assert b'No recib' in response.content

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_normalize_phone_number(self, mock_get_user, mock_process):
        """Verifica que el número de teléfono se normaliza correctamente"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573001234567')
        mock_process.return_value = {'reply': 'OK'}

        # Número con prefijo whatsapp:
        data = self.valid_data.copy()
        data['From'] = 'whatsapp:+573001234567'

        self.client.post(self.url, data=data)

        # Verificar que el número se normalizó sin el prefijo
        call_args = mock_process.call_args[1]
        assert call_args['user_id_for_security'].startswith('whatsapp_+5730')

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_permission_error_handling(self, mock_get_user, mock_process):
        """Verifica el manejo de PermissionError (usuario bloqueado)"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.side_effect = PermissionError("Usuario bloqueado")

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        assert b'Usuario bloqueado' in response.content

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_value_error_handling(self, mock_get_user, mock_process):
        """Verifica el manejo de ValueError (error de validación)"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.side_effect = ValueError("Mensaje demasiado largo")

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        assert b'Error:' in response.content
        assert b'Mensaje demasiado largo' in response.content

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_runtime_error_handling(self, mock_get_user, mock_process):
        """Verifica el manejo de RuntimeError (error del sistema)"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.side_effect = RuntimeError("Sistema no disponible")

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        assert b'temporalmente no disponible' in response.content

    @patch('bot.services_shared.process_bot_message')
    def test_unexpected_error_handling(self, mock_process):
        """Verifica el manejo de errores inesperados"""
        mock_process.side_effect = Exception("Error inesperado")

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
        assert b'error inesperado' in response.content

    def test_twiml_response_format(self):
        """Verifica que la respuesta TwiML tiene el formato correcto"""
        data = self.valid_data.copy()
        data['Body'] = ''

        response = self.client.post(self.url, data=data)

        # The response content_type should be application/xml
        assert response['Content-Type'] == 'application/xml'
        content = response.content.decode('utf-8')
        # Check for XML structure (may be wrapped in quotes if JSON-encoded by DRF)
        assert '<?xml version=' in content
        assert '<Response>' in content
        assert '</Response>' in content
        assert '<Message>' in content
        assert '</Message>' in content

    @patch('bot.services_shared.process_bot_message')
    def test_special_characters_escaped_in_twiml(self, mock_process):
        """Verifica que caracteres especiales XML se escapan correctamente"""
        mock_process.return_value = {'reply': 'Test <tag> & "quote"'}

        response = self.client.post(self.url, data=self.valid_data)

        content = response.content.decode('utf-8')
        assert '&lt;tag&gt;' in content or '<tag>' not in content.split('<Message>')[1].split('</Message>')[0]
        assert '&amp;' in content or '& ' not in content.split('<Message>')[1].split('</Message>')[0]

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_anonymous_user_phone_stored(self, mock_get_user, mock_process):
        """Verifica que el teléfono del usuario anónimo se almacena"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0', phone_number='+573157589548')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.return_value = {'reply': 'OK'}

        # Capturar el usuario anónimo pasado a process_bot_message
        self.client.post(self.url, data=self.valid_data)

        # Verificar que process_bot_message fue llamado con el anonymous_user
        call_args = mock_process.call_args[1]
        assert call_args['anonymous_user'] == anon_user
        assert call_args['user'] is None

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_passes_user_to_process_bot_message(self, mock_get_user, mock_process):
        """Verifica que pasa el usuario correcto a process_bot_message"""
        from bot.models import AnonymousUser

        # Simular que _get_user_from_phone retorna un usuario anónimo
        existing_user = baker.make(
            AnonymousUser,
            ip_address='0.0.0.0',
            phone_number='+573157589548'
        )
        mock_get_user.return_value = (None, existing_user, 'whatsapp_+573157589548')
        mock_process.return_value = {'reply': 'OK'}

        self.client.post(self.url, data=self.valid_data)

        # Verificar que se llamó con el usuario correcto
        call_args = mock_process.call_args[1]
        assert call_args['anonymous_user'] == existing_user
        assert call_args['user'] is None

    @patch('bot.services_shared.process_bot_message')
    @patch('bot.views.webhook.whatsapp_webhook.WhatsAppWebhookView._get_user_from_phone')
    def test_passes_correct_user_id_for_security(self, mock_get_user, mock_process):
        """Verifica que pasa el user_id_for_security correcto"""
        from bot.models import AnonymousUser

        anon_user = baker.make(AnonymousUser, ip_address='0.0.0.0')
        mock_get_user.return_value = (None, anon_user, 'whatsapp_+573157589548')
        mock_process.return_value = {'reply': 'OK'}

        self.client.post(self.url, data=self.valid_data)

        # Verificar que se pasó el user_id_for_security correcto
        call_args = mock_process.call_args[1]
        assert call_args['user_id_for_security'] == 'whatsapp_+573157589548'


@pytest.mark.django_db
class TestWhatsAppWebhookWithNotifications:
    """Tests para la integración con notificaciones"""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('whatsapp-webhook')
        self.valid_data = {
            'Body': 'Hola',
            'From': 'whatsapp:+573157589548',
            'MessageSid': 'SM123',
        }

    @patch('bot.services_shared.process_bot_message')
    def test_includes_last_notification_in_context(self, mock_process):
        """Verifica que incluye la última notificación en el contexto"""
        from users.models import CustomUser
        from notifications.models import NotificationLog, NotificationTemplate

        # Crear usuario y notificación
        user = baker.make(
            CustomUser,
            phone_number='+573157589548',
            is_active=True
        )

        notification_log = baker.make(
            NotificationLog,
            user=user,
            channel=NotificationTemplate.ChannelChoices.WHATSAPP,
            status=NotificationLog.Status.SENT,
            event_code='TEST_EVENT',
            payload={'subject': 'Test', 'body': 'Mensaje de prueba'}
        )

        mock_process.return_value = {'reply': 'OK'}

        self.client.post(self.url, data=self.valid_data)

        # Verificar que se pasó el contexto de notificación
        call_args = mock_process.call_args[1]
        extra_context = call_args.get('extra_context')

        assert extra_context is not None
        assert 'last_notification' in extra_context
        assert extra_context['last_notification']['event_code'] == 'TEST_EVENT'
        assert extra_context['last_notification']['channel'] == 'WhatsApp'

    @patch('bot.services_shared.process_bot_message')
    def test_no_notification_context_when_none_exists(self, mock_process):
        """Verifica que no pasa contexto de notificación si no existe"""
        from users.models import CustomUser

        # Crear usuario sin notificaciones
        baker.make(
            CustomUser,
            phone_number='+573157589548',
            is_active=True
        )

        mock_process.return_value = {'reply': 'OK'}

        self.client.post(self.url, data=self.valid_data)

        # Verificar que no hay contexto de notificación
        call_args = mock_process.call_args[1]
        extra_context = call_args.get('extra_context')

        assert extra_context is None


@pytest.mark.django_db
class TestWhatsAppWebhookSignatureValidation:
    """Tests para la validación de firma de Twilio"""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('whatsapp-webhook')
        self.valid_data = {
            'Body': 'Test',
            'From': 'whatsapp:+573157589548',
            'MessageSid': 'SM123',
        }

    @patch('bot.services_shared.process_bot_message')
    def test_signature_validation_disabled_by_default(self, mock_process, settings):
        """Verifica que la validación de firma está desactivada por defecto"""
        settings.VALIDATE_TWILIO_SIGNATURE = False
        mock_process.return_value = {'reply': 'OK'}

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200

    @patch('bot.services_shared.process_bot_message')
    @patch('twilio.request_validator.RequestValidator')
    def test_signature_validation_with_valid_signature(self, mock_validator_cls, mock_process, settings):
        """Verifica el manejo de firma válida"""
        settings.VALIDATE_TWILIO_SIGNATURE = True
        settings.TWILIO_AUTH_TOKEN = 'test_token'

        mock_validator = mock_validator_cls.return_value
        mock_validator.validate.return_value = True

        mock_process.return_value = {'reply': 'OK'}

        response = self.client.post(
            self.url,
            data=self.valid_data,
            HTTP_X_TWILIO_SIGNATURE='valid_signature'
        )

        assert response.status_code == 200

    @patch('twilio.request_validator.RequestValidator')
    def test_signature_validation_with_invalid_signature(self, mock_validator_cls, settings):
        """Verifica el rechazo de firma inválida"""
        settings.VALIDATE_TWILIO_SIGNATURE = True
        settings.TWILIO_AUTH_TOKEN = 'test_token'

        mock_validator = mock_validator_cls.return_value
        mock_validator.validate.return_value = False

        response = self.client.post(
            self.url,
            data=self.valid_data,
            HTTP_X_TWILIO_SIGNATURE='invalid_signature'
        )

        assert response.status_code == 403
        assert b'Error de autenticaci' in response.content

    @patch('bot.services_shared.process_bot_message')
    def test_signature_validation_without_auth_token(self, mock_process, settings):
        """Verifica que sin auth token se salta la validación"""
        settings.VALIDATE_TWILIO_SIGNATURE = True
        settings.TWILIO_AUTH_TOKEN = ''

        mock_process.return_value = {'reply': 'OK'}

        response = self.client.post(self.url, data=self.valid_data)

        assert response.status_code == 200
