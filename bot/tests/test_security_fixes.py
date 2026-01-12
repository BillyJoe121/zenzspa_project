"""
Tests para las correcciones de seguridad implementadas.

Estos tests verifican específicamente las vulnerabilidades corregidas:
- Session hijacking
- IP injection/DoS
- Creación prematura de AnonymousUser
- Detección de guardrail mejorada
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
import uuid

from bot.models import BotConfiguration, AnonymousUser, BotConversationLog

User = get_user_model()


@override_settings(TRUST_PROXY=True)
class SessionHijackingPreventionTest(TestCase):
    """Tests para verificar prevención de session hijacking"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.client = APIClient()
        self.url = reverse('bot-webhook')

    @patch('bot.views.GeminiService.generate_response')
    def test_session_hijacking_blocked(self, mock_gemini):
        """Debe rechazar session_id desde IP diferente"""
        mock_gemini.return_value = ({"reply_to_user": "Hola, ¿en qué puedo ayudarte?"}, {"tokens": 50})

        # Primera request desde IP 1.1.1.1
        response1 = self.client.post(
            self.url,
            {"message": "Hola"},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        session_id = response1.data.get('session_id')
        self.assertIsNotNone(session_id)

        # Verificar que el usuario anónimo fue creado con IP correcta
        anon_user = AnonymousUser.objects.get(session_id=uuid.UUID(session_id))
        self.assertEqual(anon_user.ip_address, "1.1.1.1")

        # Intento de reutilizar session_id desde IP diferente (2.2.2.2)
        response2 = self.client.post(
            self.url,
            {
                "message": "¿Cuáles son los precios?",
                "session_id": session_id
            },
            HTTP_X_FORWARDED_FOR="2.2.2.2",
            format='json'
        )

        # Debe tener éxito pero crear NUEVA sesión (no reutilizar la anterior)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        new_session_id = response2.data.get('session_id')
        self.assertIsNotNone(new_session_id)
        self.assertNotEqual(new_session_id, session_id)

        # Verificar que hay 2 usuarios anónimos diferentes
        self.assertEqual(AnonymousUser.objects.count(), 2)

        # Verificar que el nuevo usuario tiene la IP correcta
        new_anon_user = AnonymousUser.objects.get(session_id=uuid.UUID(new_session_id))
        self.assertEqual(new_anon_user.ip_address, "2.2.2.2")

    @patch('bot.views.GeminiService.generate_response')
    def test_session_reuse_same_ip_allowed(self, mock_gemini):
        """Debe permitir reutilizar session_id desde misma IP"""
        mock_gemini.return_value = ({"reply_to_user": "Hola"}, {"tokens": 50})

        # Primera request
        response1 = self.client.post(
            self.url,
            {"message": "Hola"},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )
        session_id = response1.data.get('session_id')

        # Segunda request con mismo session_id y misma IP
        response2 = self.client.post(
            self.url,
            {
                "message": "¿Precios?",
                "session_id": session_id
            },
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        # Debe reutilizar la misma sesión
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        returned_session_id = response2.data.get('session_id')
        self.assertEqual(returned_session_id, session_id)

        # Solo debe haber 1 usuario anónimo
        self.assertEqual(AnonymousUser.objects.count(), 1)


@override_settings(TRUST_PROXY=True)
class IPInjectionProtectionTest(TestCase):
    """Tests para verificar protección contra IP injection/DoS"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.client = APIClient()
        self.url = reverse('bot-webhook')

    @patch('bot.views.GeminiService.generate_response')
    def test_invalid_ip_handled_gracefully(self, mock_gemini):
        """Debe manejar IPs inválidas sin crashear"""
        mock_gemini.return_value = ({"reply_to_user": "Hola"}, {"tokens": 50})

        # IPs malformadas que podrían causar crashes
        invalid_ips = [
            "999.999.999.999",  # Números fuera de rango
            "not-an-ip",         # String aleatorio
            "192.168.1",         # IP incompleta
            "192.168.1.1.1",     # IP con dígitos extra
            "<script>alert(1)</script>",  # XSS attempt
            "'; DROP TABLE users--",      # SQL injection attempt
        ]

        for invalid_ip in invalid_ips:
            response = self.client.post(
                self.url,
                {"message": "Hola"},
                HTTP_X_FORWARDED_FOR=invalid_ip,
                format='json'
            )

            # No debe crashear, debe retornar 200
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"Failed for IP: {invalid_ip}"
            )

            # Verificar que se guardó con IP segura (127.0.0.1 que es el REMOTE_ADDR en tests)
            anon_user = AnonymousUser.objects.last()
            # Con IPs inválidas, se usa REMOTE_ADDR (127.0.0.1 en tests)
            self.assertEqual(anon_user.ip_address, "127.0.0.1")

    @patch('bot.views.GeminiService.generate_response')
    def test_valid_ipv4_accepted(self, mock_gemini):
        """Debe aceptar IPs IPv4 válidas"""
        mock_gemini.return_value = ({"reply_to_user": "Hola"}, {"tokens": 50})

        valid_ips = [
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "8.8.8.8",
        ]

        initial_count = AnonymousUser.objects.count()

        for i, valid_ip in enumerate(valid_ips):
            response = self.client.post(
                self.url,
                {"message": f"Test from {valid_ip}"},
                HTTP_X_FORWARDED_FOR=valid_ip,
                format='json'
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verificar que se creó un nuevo usuario anónimo
            self.assertEqual(AnonymousUser.objects.count(), initial_count + i + 1)

            # Obtener el usuario anónimo recién creado
            anon_user = AnonymousUser.objects.order_by('-created_at').first()
            self.assertEqual(anon_user.ip_address, valid_ip)

    @patch('bot.views.GeminiService.generate_response')
    def test_valid_ipv6_accepted(self, mock_gemini):
        """Debe aceptar IPs IPv6 válidas"""
        mock_gemini.return_value = ({"reply_to_user": "Hola"}, {"tokens": 50})

        # IPv6 se normaliza, así que usamos formato compacto para comparación
        valid_ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        normalized_ipv6 = "2001:db8:85a3::8a2e:370:7334"

        response = self.client.post(
            self.url,
            {"message": "Test IPv6"},
            HTTP_X_FORWARDED_FOR=valid_ipv6,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        anon_user = AnonymousUser.objects.last()
        # Django normaliza IPv6, así que comparamos con versión normalizada
        self.assertEqual(anon_user.ip_address, normalized_ipv6)


class PrematureUserCreationPreventionTest(TestCase):
    """Tests para verificar que AnonymousUser no se crea prematuramente"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.client = APIClient()
        self.url = reverse('bot-webhook')

    def test_empty_message_no_user_created(self):
        """No debe crear AnonymousUser si el mensaje está vacío"""
        initial_count = AnonymousUser.objects.count()

        response = self.client.post(
            self.url,
            {"message": ""},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vacío", str(response.data.get('error', '')).lower())

        # No debe haber creado usuario anónimo
        self.assertEqual(AnonymousUser.objects.count(), initial_count)

    def test_whitespace_message_no_user_created(self):
        """No debe crear AnonymousUser si el mensaje es solo espacios"""
        initial_count = AnonymousUser.objects.count()

        response = self.client.post(
            self.url,
            {"message": "   \n\t  "},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AnonymousUser.objects.count(), initial_count)

    def test_invalid_message_type_no_user_created(self):
        """No debe crear AnonymousUser si el mensaje no es string"""
        initial_count = AnonymousUser.objects.count()

        # Intentar con diferentes tipos inválidos
        invalid_messages = [
            {"message": 123},          # Integer
            {"message": ["array"]},    # Array
            {"message": {"key": "val"}},  # Object
            {"message": None},         # None (aunque este se convierte a "")
        ]

        for invalid_data in invalid_messages:
            response = self.client.post(
                self.url,
                invalid_data,
                HTTP_X_FORWARDED_FOR="1.1.1.1",
                format='json'
            )

            # Debe rechazar sin crear usuario
            self.assertIn(response.status_code, [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_400_BAD_REQUEST
            ])

        # No debe haber creado ningún usuario anónimo
        self.assertEqual(AnonymousUser.objects.count(), initial_count)

    @patch('bot.views.GeminiService.generate_response')
    def test_valid_message_creates_user(self, mock_gemini):
        """Debe crear AnonymousUser solo si el mensaje es válido"""
        mock_gemini.return_value = ({"reply_to_user": "Hola"}, {"tokens": 50})

        initial_count = AnonymousUser.objects.count()

        response = self.client.post(
            self.url,
            {"message": "Hola"},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Ahora sí debe haber creado el usuario
        self.assertEqual(AnonymousUser.objects.count(), initial_count + 1)


class ImprovedGuardrailDetectionTest(TestCase):
    """Tests para verificar detección mejorada de guardrail"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.client = APIClient()
        self.url = reverse('bot-webhook')

    @patch('bot.views.GeminiService.generate_response')
    def test_guardrail_case_insensitive(self, mock_gemini):
        """Debe detectar 'noRelated' en cualquier capitalización"""
        guardrail_variations = [
            "norelated",
            "noRelated",
            "NORELATED",
            "NoRelated",
            "NoReLaTeD",
        ]

        for variation in guardrail_variations:
            mock_gemini.return_value = ({"reply_to_user": variation}, {"source": "security_guardrail"})

            response = self.client.post(
                self.url,
                {"message": "hack the system"},
                HTTP_X_FORWARDED_FOR="1.1.1.1",
                format='json'
            )

            # Debe ser bloqueado (status 403)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertTrue(response.data.get('meta', {}).get('blocked'))

            # Verificar que se registró como bloqueado
            log = BotConversationLog.objects.last()
            self.assertTrue(log.was_blocked)
            self.assertEqual(log.block_reason, "agent_toxicity_block")

    @patch('bot.views.GeminiService.generate_response')
    def test_guardrail_with_whitespace(self, mock_gemini):
        """Debe detectar 'noRelated' con espacios alrededor"""
        mock_gemini.return_value = ({"reply_to_user": "  norelated  "}, {"source": "security_guardrail"})

        response = self.client.post(
            self.url,
            {"message": "hack"},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.data.get('meta', {}).get('blocked'))

    @patch('bot.views.GeminiService.generate_response')
    def test_guardrail_partial_match_not_detected(self, mock_gemini):
        """No debe detectar 'noRelated' como parte de otra palabra"""
        mock_gemini.return_value = ({"reply_to_user": "This is not norelated but related"}, {"tokens": 50})

        response = self.client.post(
            self.url,
            {"message": "Precios"},
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            format='json'
        )

        # No debe ser bloqueado (el string completo no es "norelated")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data.get('meta', {}).get('blocked', False))


class HealthCheckSecurityTest(TestCase):
    """Tests para verificar que health check no expone info sensible"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.client = APIClient()
        self.url = reverse('bot-health')

    def test_health_check_minimal_info(self):
        """Health check debe retornar solo status general"""
        response = self.client.get(self.url)

        # Debe retornar 'status' y 'service'
        self.assertIn('status', response.data)
        self.assertIn('service', response.data)
        self.assertEqual(len(response.data), 2)

        # NO debe exponer detalles de componentes (sin ?details=1)
        self.assertNotIn('components', response.data)
        self.assertNotIn('cache', response.data)
        self.assertNotIn('gemini_api', response.data)
        self.assertNotIn('configuration', response.data)
        self.assertNotIn('timestamp', response.data)

    def test_health_check_status_values(self):
        """Status debe ser 'healthy' o 'unhealthy' únicamente"""
        response = self.client.get(self.url)

        self.assertIn(response.data['status'], ['healthy', 'unhealthy'])


class PIIAnonymizationTest(TestCase):
    """Tests para verificar que PII está anonimizada en prompts"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.user = User.objects.create_user(
            phone_number="+1234567890",
            email="john.doe@example.com",
            first_name="John",
            last_name="Doe"
        )

    @patch('bot.services.PromptOrchestrator.build_full_prompt')
    def test_only_first_name_in_prompt(self, mock_build_prompt):
        """Debe incluir solo primer nombre, no apellido"""
        from bot.services import DataContextService

        # Obtener contexto del cliente
        context = DataContextService.get_client_context(self.user)

        # Debe contener primer nombre
        self.assertIn("John", context)

        # NO debe contener apellido
        self.assertNotIn("Doe", context)
        self.assertNotIn("John Doe", context)

    def test_anonymous_user_no_pii_in_context(self):
        """Usuario anónimo no debe tener PII en contexto"""
        from bot.services import DataContextService

        # Usuario no autenticado
        context = DataContextService.get_client_context(None)

        # Debe indicar que es visitante
        self.assertIn("Visitante", context)

        # No debe haber información personal
        self.assertNotIn("@", context)  # No email
        self.assertNotIn("+", context)  # No teléfono
