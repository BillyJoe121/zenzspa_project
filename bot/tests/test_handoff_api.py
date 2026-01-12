"""
Tests para los endpoints de la API de handoff humano.
"""
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from bot.models import (
    BotConfiguration, BotConversationLog, AnonymousUser,
    HumanHandoffRequest, HumanMessage
)

User = get_user_model()


class HumanHandoffRequestViewSetTest(TestCase):
    """Tests para el ViewSet de HumanHandoffRequest"""

    def setUp(self):
        """Setup común para tests de API"""
        self.client = APIClient()

        # Crear configuración
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

        # Crear usuarios
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
        self.regular_user = User.objects.create_user(
            phone_number="+3333333333",
            email="client@example.com",
            first_name="Client"
        )

        # Crear log y handoff
        self.log = BotConversationLog.objects.create(
            user=self.regular_user,
            message="Quiero hablar con alguien",
            response="Te conecto",
            tokens_used=100
        )
        self.handoff = HumanHandoffRequest.objects.create(
            user=self.regular_user,
            conversation_log=self.log,
            client_score=75,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            conversation_context={'last_message': 'Quiero ayuda'},
            client_interests={'services_mentioned': ['Masaje']}
        )

    def tearDown(self):
        """Limpiar datos después de cada test"""
        HumanHandoffRequest.objects.all().delete()
        BotConversationLog.objects.all().delete()
        User.objects.all().delete()
        BotConfiguration.objects.all().delete()

    def _get_results(self, response):
        """Helper para extraer resultados de respuesta paginada o no"""
        if 'results' in response.data:
            return response.data['results']
        return response.data

    def test_list_handoffs_as_staff(self):
        """Staff debe poder listar handoffs"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._get_results(response)
        self.assertGreaterEqual(len(results), 1)
        # Verificar que nuestro handoff está en la lista
        handoff_ids = [h['id'] for h in results]
        self.assertIn(self.handoff.id, handoff_ids)

    def test_list_handoffs_as_admin(self):
        """Admin debe poder listar handoffs"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._get_results(response)
        self.assertGreaterEqual(len(results), 1)

    def test_list_handoffs_as_regular_user(self):
        """Usuario regular no debe poder listar handoffs"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._get_results(response)
        # Regular users get empty queryset
        self.assertEqual(len(results), 0)

    def test_list_handoffs_unauthenticated(self):
        """Usuario no autenticado no debe poder listar handoffs"""
        url = reverse('handoff-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_handoff_as_staff(self):
        """Staff debe poder ver detalle de handoff"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-detail', kwargs={'pk': self.handoff.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.handoff.id)
        self.assertEqual(response.data['client_score'], 75)
        self.assertIn('messages', response.data)

    def test_filter_by_status(self):
        """Debe poder filtrar handoffs por status"""
        # Crear otro handoff asignado
        log2 = BotConversationLog.objects.create(
            user=self.regular_user,
            message="Test",
            response="Response",
            tokens_used=50
        )
        assigned_handoff = HumanHandoffRequest.objects.create(
            user=self.regular_user,
            conversation_log=log2,
            client_score=60,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.ASSIGNED,
            assigned_to=self.staff
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-list')

        # Filtrar por PENDING
        response = self.client.get(url, {'status': 'PENDING'})
        results = self._get_results(response)
        self.assertGreaterEqual(len(results), 1)
        # Verificar que hay al menos un PENDING
        pending_found = any(h['status'] == 'PENDING' for h in results)
        self.assertTrue(pending_found)

        # Filtrar por ASSIGNED
        response = self.client.get(url, {'status': 'ASSIGNED'})
        results = self._get_results(response)
        self.assertGreaterEqual(len(results), 1)
        # Verificar que hay al menos un ASSIGNED
        assigned_found = any(h['status'] == 'ASSIGNED' for h in results)
        self.assertTrue(assigned_found)

    def test_filter_assigned_to_me(self):
        """Debe filtrar handoffs asignados al usuario"""
        # Asignar handoff al staff
        self.handoff.assigned_to = self.staff
        self.handoff.status = HumanHandoffRequest.Status.ASSIGNED
        self.handoff.save()

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-list')

        response = self.client.get(url, {'assigned_to_me': 'true'})

        results = self._get_results(response)
        self.assertGreaterEqual(len(results), 1)
        # Verificar que todos los handoffs están asignados al staff
        for handoff in results:
            self.assertEqual(handoff['assigned_to'], self.staff.id)

    def test_assign_action(self):
        """Debe asignar handoff al usuario actual"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-assign', kwargs={'pk': self.handoff.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar cambios en DB
        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.assigned_to, self.staff)
        self.assertEqual(self.handoff.status, HumanHandoffRequest.Status.ASSIGNED)
        self.assertIsNotNone(self.handoff.assigned_at)

    def test_assign_action_already_assigned(self):
        """No debe reasignar handoff ya asignado"""
        # Asignar a admin primero
        self.handoff.assigned_to = self.admin
        self.handoff.status = HumanHandoffRequest.Status.ASSIGNED
        self.handoff.assigned_at = timezone.now()
        self.handoff.save()

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-assign', kwargs={'pk': self.handoff.pk})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('PENDING', str(response.data))

    def test_resolve_action(self):
        """Debe marcar handoff como resuelto"""
        # Primero asignar
        self.handoff.assigned_to = self.staff
        self.handoff.status = HumanHandoffRequest.Status.ASSIGNED
        self.handoff.save()

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-resolve', kwargs={'pk': self.handoff.pk})

        data = {'resolution_notes': 'Cliente satisfecho'}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar cambios
        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.status, HumanHandoffRequest.Status.RESOLVED)
        self.assertIsNotNone(self.handoff.resolved_at)
        self.assertIn('Cliente satisfecho', self.handoff.internal_notes)

    def test_resolve_action_not_assigned(self):
        """No debe resolver handoff que no está asignado"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-resolve', kwargs={'pk': self.handoff.pk})

        response = self.client.post(url, {'resolution_notes': 'Test'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_messages_action(self):
        """Debe listar mensajes del handoff"""
        # Crear mensajes
        msg1 = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.regular_user,
            is_from_staff=False,
            message="Hola, necesito ayuda"
        )
        msg2 = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.staff,
            is_from_staff=True,
            message="Claro, ¿en qué te puedo ayudar?"
        )

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-messages', kwargs={'pk': self.handoff.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_messages_action_marks_as_read(self):
        """Debe marcar mensajes del cliente como leídos"""
        # Crear mensaje del cliente no leído
        msg = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.regular_user,
            is_from_staff=False,
            message="Hola"
        )

        self.assertIsNone(msg.read_at)

        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-messages', kwargs={'pk': self.handoff.pk})

        response = self.client.get(url)

        # Verificar que se marcó como leído
        msg.refresh_from_db()
        self.assertIsNotNone(msg.read_at)

    def test_send_message_action(self):
        """Debe enviar mensaje del staff al cliente"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-send-message', kwargs={'pk': self.handoff.pk})

        data = {
            'message': 'Hola, ¿en qué puedo ayudarte?'
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verificar que se creó el mensaje
        message = HumanMessage.objects.filter(
            handoff_request=self.handoff,
            sender=self.staff,
            is_from_staff=True
        ).first()

        self.assertIsNotNone(message)
        self.assertEqual(message.message, 'Hola, ¿en qué puedo ayudarte?')

    def test_send_message_action_empty_message(self):
        """No debe permitir enviar mensaje vacío"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-send-message', kwargs={'pk': self.handoff.pk})

        data = {'message': ''}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_handoff_status(self):
        """Staff debe poder actualizar status del handoff"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-detail', kwargs={'pk': self.handoff.pk})

        data = {
            'status': 'IN_PROGRESS',
            'internal_notes': 'Trabajando en ello'
        }
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.status, HumanHandoffRequest.Status.IN_PROGRESS)
        self.assertEqual(self.handoff.internal_notes, 'Trabajando en ello')

    def test_cannot_update_readonly_fields(self):
        """No debe permitir actualizar campos readonly"""
        self.client.force_authenticate(user=self.staff)
        url = reverse('handoff-detail', kwargs={'pk': self.handoff.pk})

        data = {
            'client_score': 100,  # readonly
            'escalation_reason': 'HIGH_VALUE_CLIENT'  # readonly
        }
        response = self.client.patch(url, data)

        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.client_score, 75)  # No cambió
        self.assertEqual(
            self.handoff.escalation_reason,
            HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )  # No cambió


class HandoffSerializerTest(TestCase):
    """Tests para los serializers de handoff"""

    def setUp(self):
        """Setup común para tests de serializers"""
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )
        self.user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test",
            last_name="User"
        )
        self.staff = User.objects.create_user(
            phone_number="+9876543210",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.log = BotConversationLog.objects.create(
            user=self.user,
            message="Test",
            response="Response",
            tokens_used=100
        )
        self.handoff = HumanHandoffRequest.objects.create(
            user=self.user,
            conversation_log=self.log,
            client_score=80,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST
        )

    def test_handoff_detail_serializer(self):
        """Debe serializar handoff con todos los detalles"""
        from bot.serializers import HumanHandoffRequestDetailSerializer

        serializer = HumanHandoffRequestDetailSerializer(self.handoff)
        data = serializer.data

        self.assertEqual(data['id'], self.handoff.id)
        self.assertEqual(data['client_score'], 80)
        self.assertEqual(data['status'], 'PENDING')
        self.assertIn('messages', data)
        self.assertIn('client_identifier', data)

    def test_handoff_list_serializer(self):
        """Debe serializar handoff en vista resumida"""
        from bot.serializers import HumanHandoffRequestListSerializer

        serializer = HumanHandoffRequestListSerializer(self.handoff)
        data = serializer.data

        self.assertEqual(data['id'], self.handoff.id)
        self.assertIn('client_identifier', data)
        self.assertIn('unread_messages_count', data)

    def test_message_create_serializer_staff(self):
        """Debe crear mensaje del staff correctamente"""
        from bot.serializers import HumanMessageCreateSerializer
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import AnonymousUser as DjangoAnonymousUser

        factory = APIRequestFactory()
        request = factory.post('/fake')
        request.user = self.staff

        data = {
            'handoff_request': self.handoff.id,
            'message': 'Hola desde staff'
        }

        serializer = HumanMessageCreateSerializer(
            data=data,
            context={'request': request}
        )

        self.assertTrue(serializer.is_valid())
        message = serializer.save()

        self.assertEqual(message.sender, self.staff)
        self.assertTrue(message.is_from_staff)
        self.assertFalse(message.from_anonymous)

    def test_message_create_serializer_anonymous(self):
        """Debe crear mensaje de cliente anónimo correctamente"""
        from bot.serializers import HumanMessageCreateSerializer
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import AnonymousUser as DjangoAnonymousUser

        factory = APIRequestFactory()
        request = factory.post('/fake')
        request.user = DjangoAnonymousUser()

        data = {
            'handoff_request': self.handoff.id,
            'message': 'Hola desde cliente'
        }

        serializer = HumanMessageCreateSerializer(
            data=data,
            context={'request': request}
        )

        self.assertTrue(serializer.is_valid())
        message = serializer.save()

        self.assertIsNone(message.sender)
        self.assertFalse(message.is_from_staff)
        self.assertTrue(message.from_anonymous)

    def test_message_serializer_validation(self):
        """Debe validar que mensajes del staff tengan sender"""
        from bot.serializers import HumanMessageSerializer

        data = {
            'handoff_request': self.handoff.id,
            'is_from_staff': True,
            'message': 'Test'
            # Falta sender
        }

        serializer = HumanMessageSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_handoff_update_serializer(self):
        """Debe actualizar handoff correctamente"""
        from bot.serializers import HumanHandoffRequestUpdateSerializer

        data = {
            'status': 'IN_PROGRESS',
            'internal_notes': 'Working on it'
        }

        serializer = HumanHandoffRequestUpdateSerializer(
            self.handoff,
            data=data,
            partial=True
        )

        self.assertTrue(serializer.is_valid())
        updated_handoff = serializer.save()

        self.assertEqual(updated_handoff.status, HumanHandoffRequest.Status.IN_PROGRESS)
        self.assertEqual(updated_handoff.internal_notes, 'Working on it')

    def test_handoff_update_auto_assign_timestamp(self):
        """Debe asignar timestamp automáticamente al asignar"""
        from bot.serializers import HumanHandoffRequestUpdateSerializer

        data = {
            'assigned_to': self.staff.id,
            'status': 'ASSIGNED'
        }

        serializer = HumanHandoffRequestUpdateSerializer(
            self.handoff,
            data=data,
            partial=True
        )

        self.assertTrue(serializer.is_valid())
        updated_handoff = serializer.save()

        self.assertEqual(updated_handoff.assigned_to, self.staff)
        self.assertIsNotNone(updated_handoff.assigned_at)
