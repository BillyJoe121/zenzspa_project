"""
Tests de sad paths y edge cases para el sistema de handoff humano.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status
from datetime import timedelta

from bot.models import (
    BotConfiguration, BotConversationLog, AnonymousUser,
    HumanHandoffRequest, HumanMessage
)

User = get_user_model()


class HumanHandoffRequestValidationTest(TestCase):
    """Tests de validación del modelo HumanHandoffRequest"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test"
        )
        self.log = BotConversationLog.objects.create(
            user=self.user,
            message="Help",
            response="Response",
            tokens_used=50
        )

    def test_cannot_have_both_user_and_anonymous(self):
        """No debe permitir usuario registrado Y anónimo simultáneamente"""
        anonymous = AnonymousUser.objects.create(ip_address="127.0.0.1")

        handoff = HumanHandoffRequest(
            user=self.user,
            anonymous_user=anonymous,
            conversation_log=self.log,
            client_score=50,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        with self.assertRaises(ValidationError):
            handoff.full_clean()

    def test_must_have_user_or_anonymous(self):
        """Debe tener al menos usuario registrado O anónimo"""
        handoff = HumanHandoffRequest(
            user=None,
            anonymous_user=None,
            conversation_log=self.log,
            client_score=50,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        with self.assertRaises(ValidationError):
            handoff.full_clean()

    def test_client_score_within_range(self):
        """client_score debe estar en rango válido (0-100)"""
        # Score válido
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=85,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )
        self.assertEqual(handoff.client_score, 85)

        # Aunque Django no valida rangos por defecto, podemos testear valores extremos
        handoff_low = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=0,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )
        self.assertEqual(handoff_low.client_score, 0)

        handoff_high = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=100,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )
        self.assertEqual(handoff_high.client_score, 100)


class HumanHandoffRequestPropertiesTest(TestCase):
    """Tests para propiedades calculadas de HumanHandoffRequest"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.user = User.objects.create_user(
            phone_number="+1234567890",
            email="john@example.com",
            first_name="John",
            last_name="Doe"
        )
        self.log = BotConversationLog.objects.create(
            user=self.user,
            message="Help",
            response="Response",
            tokens_used=50
        )

    def test_client_contact_info_registered_user(self):
        """client_contact_info debe retornar info completa de usuario registrado"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        info = handoff.client_contact_info

        self.assertIn('name', info)
        self.assertIn('phone', info)
        self.assertIn('email', info)
        self.assertEqual(info['phone'], "+1234567890")
        self.assertEqual(info['email'], "john@example.com")

    def test_client_contact_info_anonymous_partial(self):
        """client_contact_info debe manejar usuario anónimo con info parcial"""
        anonymous = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="Jane",
            email="jane@example.com"
            # phone_number no proporcionado
        )
        log = BotConversationLog.objects.create(
            anonymous_user=anonymous,
            message="Help",
            response="Response",
            tokens_used=50
        )
        handoff = HumanHandoffRequest.objects.create(
            anonymous_user=anonymous,
            conversation_log=log,
            client_score=50,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        info = handoff.client_contact_info

        self.assertEqual(info['name'], "Jane")
        self.assertEqual(info['email'], "jane@example.com")
        self.assertEqual(info['phone'], "No proporcionado")

    def test_response_time_not_assigned(self):
        """response_time debe ser None si no está asignado"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.PENDING
        )

        self.assertIsNone(handoff.response_time)

    def test_response_time_calculated_correctly(self):
        """response_time debe calcular minutos correctamente"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        # Simular asignación 45 minutos después
        handoff.assigned_at = handoff.created_at + timedelta(minutes=45)
        handoff.save()

        self.assertEqual(handoff.response_time, 45)

    def test_resolution_time_not_resolved(self):
        """resolution_time debe ser None si no está resuelto"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.ASSIGNED
        )

        self.assertIsNone(handoff.resolution_time)

    def test_resolution_time_calculated_correctly(self):
        """resolution_time debe calcular tiempo total correctamente"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        # Simular resolución 2 horas después
        handoff.resolved_at = handoff.created_at + timedelta(hours=2)
        handoff.save()

        self.assertEqual(handoff.resolution_time, 120)  # 2 horas = 120 minutos

    def test_is_active_pending(self):
        """is_active debe ser True para status PENDING"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.PENDING
        )

        self.assertTrue(handoff.is_active)

    def test_is_active_assigned(self):
        """is_active debe ser True para status ASSIGNED"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.ASSIGNED
        )

        self.assertTrue(handoff.is_active)

    def test_is_active_resolved(self):
        """is_active debe ser False para status RESOLVED"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.RESOLVED
        )

        self.assertFalse(handoff.is_active)

    def test_is_active_cancelled(self):
        """is_active debe ser False para status CANCELLED"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.CANCELLED
        )

        self.assertFalse(handoff.is_active)


class HumanHandoffAPIPermissionsTest(TestCase):
    """Tests de permisos para la API de handoff"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.admin = User.objects.create_user(
            phone_number="+1111111111",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            phone_number="+2222222222",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.regular = User.objects.create_user(
            phone_number="+3333333333",
            email="regular@example.com",
            first_name="Regular"
        )
        self.log = BotConversationLog.objects.create(
            user=self.regular,
            message="Help",
            response="Response",
            tokens_used=50
        )
        self.handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )
        self.client = APIClient()

    def test_anonymous_cannot_access_handoffs(self):
        """Usuario anónimo no debe poder acceder a handoffs"""
        url = reverse('handoff-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_cannot_access_handoffs(self):
        """Usuario regular no debe poder acceder a handoffs"""
        self.client.force_authenticate(user=self.regular)
        url = reverse('handoff-list')

        response = self.client.get(url)

        # Retorna 200 pero con queryset vacío
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if 'results' in response.data:
            self.assertEqual(len(response.data['results']), 0)
        else:
            self.assertEqual(len(response.data), 0)

    def test_staff_can_access_handoffs(self):
        """Staff debe poder acceder a handoffs"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_access_handoffs(self):
        """Admin debe poder acceder a handoffs"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class HumanHandoffAPIActionsSadPathsTest(TestCase):
    """Tests de sad paths para acciones de handoff API"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.staff = User.objects.create_user(
            phone_number="+2222222222",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.regular = User.objects.create_user(
            phone_number="+3333333333",
            email="regular@example.com",
            first_name="Regular"
        )
        self.log = BotConversationLog.objects.create(
            user=self.regular,
            message="Help",
            response="Response",
            tokens_used=50
        )
        self.client = APIClient()

    def test_assign_already_assigned_handoff(self):
        """No debe poder asignar handoff ya asignado"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.ASSIGNED,
            assigned_to=self.staff
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-assign', kwargs={'pk': handoff.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('PENDING', str(response.data))

    def test_assign_resolved_handoff(self):
        """No debe poder asignar handoff resuelto"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.RESOLVED
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-assign', kwargs={'pk': handoff.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resolve_pending_handoff(self):
        """No debe poder resolver handoff que no está asignado"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.PENDING
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-resolve', kwargs={'pk': handoff.pk})

        response = self.client.post(url, {'resolution_notes': 'Done'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('asignados', str(response.data).lower())

    def test_resolve_already_resolved_handoff(self):
        """No debe poder resolver handoff ya resuelto"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.RESOLVED,
            assigned_to=self.staff,
            resolved_at=timezone.now()
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-resolve', kwargs={'pk': handoff.pk})

        response = self.client.post(url, {'resolution_notes': 'Done again'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_message_to_nonexistent_handoff(self):
        """No debe poder enviar mensaje a handoff inexistente"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-send-message', kwargs={'pk': 99999})

        response = self.client.post(url, {'message': 'Hello'})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_send_empty_message(self):
        """No debe poder enviar mensaje vacío"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.regular,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.ASSIGNED,
            assigned_to=self.staff
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-send-message', kwargs={'pk': handoff.pk})

        response = self.client.post(url, {'message': ''})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class HumanMessageTest(TestCase):
    """Tests para el modelo HumanMessage"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.staff = User.objects.create_user(
            phone_number="+2222222222",
            email="staff@example.com",
            first_name="Staff",
            last_name="User",
            role=User.Role.STAFF
        )
        self.client_user = User.objects.create_user(
            phone_number="+3333333333",
            email="client@example.com",
            first_name="Client"
        )
        self.log = BotConversationLog.objects.create(
            user=self.client_user,
            message="Help",
            response="Response",
            tokens_used=50
        )
        self.handoff = HumanHandoffRequest.objects.create(
            user=self.client_user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

    def test_sender_name_staff(self):
        """sender_name debe retornar nombre completo del staff"""
        message = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.staff,
            is_from_staff=True,
            message="Hello"
        )

        self.assertEqual(message.sender_name, "Staff User")

    def test_sender_name_anonymous_client(self):
        """sender_name debe retornar display_name del anónimo"""
        anonymous = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="Jane Doe"
        )
        log = BotConversationLog.objects.create(
            anonymous_user=anonymous,
            message="Help",
            response="Response",
            tokens_used=50
        )
        handoff = HumanHandoffRequest.objects.create(
            anonymous_user=anonymous,
            conversation_log=log,
            client_score=50,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        message = HumanMessage.objects.create(
            handoff_request=handoff,
            sender=None,
            is_from_staff=False,
            from_anonymous=True,
            message="I need help"
        )

        self.assertEqual(message.sender_name, "Jane Doe")

    def test_mark_as_read(self):
        """mark_as_read debe establecer read_at"""
        message = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.client_user,
            is_from_staff=False,
            message="Hello"
        )

        self.assertIsNone(message.read_at)
        self.assertTrue(message.is_unread)

        message.mark_as_read()
        message.refresh_from_db()

        self.assertIsNotNone(message.read_at)
        self.assertFalse(message.is_unread)

    def test_mark_as_read_idempotent(self):
        """mark_as_read debe ser idempotente"""
        message = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.client_user,
            is_from_staff=False,
            message="Hello"
        )

        message.mark_as_read()
        first_read_at = message.read_at

        # Marcar como leído de nuevo
        message.mark_as_read()

        # read_at no debe cambiar
        self.assertEqual(message.read_at, first_read_at)


class HumanHandoffJSONFieldsTest(TestCase):
    """Tests para campos JSON de handoff"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test"
        )
        self.log = BotConversationLog.objects.create(
            user=self.user,
            message="Help",
            response="Response",
            tokens_used=50
        )

    def test_conversation_context_default_empty_dict(self):
        """conversation_context debe tener dict vacío por defecto"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        self.assertEqual(handoff.conversation_context, {})
        self.assertIsInstance(handoff.conversation_context, dict)

    def test_client_interests_default_empty_dict(self):
        """client_interests debe tener dict vacío por defecto"""
        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=70,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

        self.assertEqual(handoff.client_interests, {})
        self.assertIsInstance(handoff.client_interests, dict)

    def test_conversation_context_complex_data(self):
        """conversation_context debe soportar datos complejos"""
        complex_context = {
            'last_messages': [
                {'role': 'user', 'content': 'Hola'},
                {'role': 'assistant', 'content': 'Bienvenido'}
            ],
            'total_messages': 10,
            'escalation_message': 'Necesito ayuda',
            'metadata': {
                'urgency': 'high',
                'budget_mentioned': '$5000'
            }
        }

        handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=85,
            escalation_reason=HumanHandoffRequest.EscalationReason.HIGH_VALUE_CLIENT,
            conversation_context=complex_context
        )

        handoff.refresh_from_db()

        self.assertEqual(handoff.conversation_context, complex_context)
        self.assertEqual(handoff.conversation_context['metadata']['urgency'], 'high')
