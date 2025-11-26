"""
Tests para el módulo admin del bot.

Cubre todas las funcionalidades de Django Admin:
- Permisos por rol (ADMIN, STAFF, regular users)
- Acciones personalizadas
- Displays y readonly fields
- Validaciones y restricciones
"""
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.http import HttpResponse
from unittest.mock import Mock, patch
from datetime import timedelta

from bot.models import (
    BotConfiguration, BotConversationLog, AnonymousUser,
    HumanHandoffRequest, HumanMessage, IPBlocklist, SuspiciousActivity
)
from bot.admin import (
    BotConfigurationAdmin, BotConversationLogAdmin, AnonymousUserAdmin,
    HumanHandoffRequestAdmin, HumanMessageAdmin,
    IPBlocklistAdmin, SuspiciousActivityAdmin
)

User = get_user_model()


class MockRequest:
    """Mock request object para tests de admin"""
    def __init__(self, user):
        self.user = user


class BotConfigurationAdminTest(TestCase):
    """Tests para BotConfigurationAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = BotConfigurationAdmin(BotConfiguration, self.site)
        self.factory = RequestFactory()

        # Crear usuarios de diferentes roles
        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password"
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.regular_user = User.objects.create_user(
            phone_number="+4444444444",
            email="regular@example.com",
            first_name="Regular"
        )

        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_list_display(self):
        """Debe mostrar campos correctos en lista"""
        expected = ('site_name', 'is_active', 'booking_url',
                   'api_input_price_per_1k', 'api_output_price_per_1k')
        self.assertEqual(self.admin.list_display, expected)

    def test_has_add_permission_superuser(self):
        """Superuser puede agregar configuraciones cuando no existe ninguna"""
        # Eliminar la configuración existente para probar el singleton
        BotConfiguration.objects.all().delete()
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_add_permission(request))

    def test_has_add_permission_admin(self):
        """Admin puede agregar configuraciones cuando no existe ninguna"""
        # Eliminar la configuración existente para probar el singleton
        BotConfiguration.objects.all().delete()
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_add_permission(request))

    def test_has_add_permission_staff(self):
        """Staff NO puede agregar configuraciones"""
        # Eliminar la configuración existente para probar permisos de rol
        BotConfiguration.objects.all().delete()
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_add_permission_regular(self):
        """Usuario regular NO puede agregar configuraciones"""
        # Eliminar la configuración existente para probar permisos de rol
        BotConfiguration.objects.all().delete()
        request = MockRequest(self.regular_user)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission_superuser(self):
        """Superuser puede editar configuraciones"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_admin(self):
        """Admin puede editar configuraciones"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_staff(self):
        """Staff NO puede editar configuraciones"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission_superuser(self):
        """Superuser puede eliminar configuraciones"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_admin(self):
        """Admin puede eliminar configuraciones"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_staff(self):
        """Staff NO puede eliminar configuraciones"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_delete_permission(request))


class AnonymousUserAdminTest(TestCase):
    """Tests para AnonymousUserAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = AnonymousUserAdmin(AnonymousUser, self.site)

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password"
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.regular_user = User.objects.create_user(
            phone_number="+4444444444",
            email="regular@example.com",
            first_name="Regular"
        )

        self.anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="Test User"
        )

    def test_is_expired_status_true(self):
        """is_expired_status debe retornar True para sesión expirada"""
        self.anon_user.expires_at = timezone.now() - timedelta(days=1)
        self.anon_user.save()

        self.assertTrue(self.admin.is_expired_status(self.anon_user))

    def test_is_expired_status_false(self):
        """is_expired_status debe retornar False para sesión válida"""
        self.assertFalse(self.admin.is_expired_status(self.anon_user))

    def test_converted_status_true(self):
        """converted_status debe retornar True si está convertido"""
        user = User.objects.create_user(
            phone_number="+5555555555",
            email="converted@example.com",
            first_name="Converted"
        )
        self.anon_user.converted_to_user = user
        self.anon_user.save()

        self.assertTrue(self.admin.converted_status(self.anon_user))

    def test_converted_status_false(self):
        """converted_status debe retornar False si no está convertido"""
        self.assertFalse(self.admin.converted_status(self.anon_user))

    def test_has_add_permission(self):
        """Nadie puede agregar usuarios anónimos manualmente"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission_superuser(self):
        """Superuser puede editar usuarios anónimos"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_admin(self):
        """Admin puede editar usuarios anónimos"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_staff(self):
        """Staff NO puede editar usuarios anónimos"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission_superuser(self):
        """Superuser puede eliminar usuarios anónimos"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_admin(self):
        """Admin puede eliminar usuarios anónimos"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_staff(self):
        """Staff NO puede eliminar usuarios anónimos"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_has_view_permission_staff(self):
        """Staff puede ver usuarios anónimos"""
        request = MockRequest(self.staff_user)
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_regular(self):
        """Usuario regular NO puede ver usuarios anónimos"""
        request = MockRequest(self.regular_user)
        self.assertFalse(self.admin.has_view_permission(request))


class BotConversationLogAdminTest(TestCase):
    """Tests para BotConversationLogAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = BotConversationLogAdmin(BotConversationLog, self.site)
        self.factory = RequestFactory()

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password"
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )

        self.user = User.objects.create_user(
            phone_number="+4444444444",
            email="user@example.com",
            first_name="User"
        )

        self.log = BotConversationLog.objects.create(
            user=self.user,
            message="Test message",
            response="Test response",
            tokens_used=50
        )

    def test_participant_display_registered_user(self):
        """participant_display debe mostrar teléfono del usuario"""
        display = self.admin.participant_display(self.log)
        self.assertEqual(display, "+4444444444")

    def test_participant_display_anonymous_user(self):
        """participant_display debe mostrar nombre del anónimo"""
        anon = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="Anonymous Test"
        )
        log = BotConversationLog.objects.create(
            anonymous_user=anon,
            message="Test",
            response="Response",
            tokens_used=30
        )

        display = self.admin.participant_display(log)
        self.assertEqual(display, "Anonymous Test")

    def test_has_add_permission(self):
        """Nadie puede crear logs manualmente"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission(self):
        """Nadie puede editar logs (readonly)"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission_superuser(self):
        """Superuser puede eliminar logs"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_admin(self):
        """Admin puede eliminar logs"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_staff(self):
        """Staff NO puede eliminar logs"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_has_view_permission_superuser(self):
        """Superuser puede ver logs"""
        request = MockRequest(self.superuser)
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_admin(self):
        """Admin puede ver logs"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_staff(self):
        """Staff NO puede ver logs (privacidad)"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_view_permission(request))

    def test_changelist_view_adds_extra_context(self):
        """changelist_view debe agregar top_ips y analysis_period al contexto."""
        BotConversationLog.objects.create(
            user=self.user,
            message="Hi",
            response="There",
            tokens_used=5,
            ip_address="9.9.9.9",
        )

        request = self.factory.get("/admin/bot/botconversationlog/")
        request.user = self.superuser

        with patch(
            "bot.admin.admin.ModelAdmin.changelist_view", return_value=HttpResponse("ok")
        ) as mocked_super:
            response = self.admin.changelist_view(request)

        self.assertEqual(response.content, b"ok")
        extra = mocked_super.call_args.kwargs["extra_context"]
        self.assertIn("top_ips", extra)
        self.assertEqual(extra["analysis_period"], "7 días")


class HumanHandoffRequestAdminTest(TestCase):
    """Tests para HumanHandoffRequestAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = HumanHandoffRequestAdmin(HumanHandoffRequest, self.site)

        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password"
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )
        self.regular_user = User.objects.create_user(
            phone_number="+4444444444",
            email="regular@example.com",
            first_name="Regular"
        )

        self.client_user = User.objects.create_user(
            phone_number="+5555555555",
            email="client@example.com",
            first_name="Client"
        )

        self.log = BotConversationLog.objects.create(
            user=self.client_user,
            message="Need help",
            response="Response",
            tokens_used=50
        )

        self.handoff = HumanHandoffRequest.objects.create(
            user=self.client_user,
            conversation_log=self.log,
            client_score=75,
            escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
            status=HumanHandoffRequest.Status.PENDING
        )

    def test_client_contact_display(self):
        """client_contact_display debe formatear info correctamente"""
        display = self.admin.client_contact_display(self.handoff)

        self.assertIn("Client", display)
        self.assertIn("+5555555555", display)
        self.assertIn("client@example.com", display)

    def test_conversation_context_display(self):
        """conversation_context_display debe retornar JSON formateado"""
        self.handoff.conversation_context = {'key': 'value', 'nested': {'data': 123}}
        self.handoff.save()

        display = self.admin.conversation_context_display(self.handoff)

        self.assertIn('"key"', display)
        self.assertIn('"value"', display)
        self.assertIn('"nested"', display)

    def test_client_interests_display(self):
        """client_interests_display debe retornar JSON formateado"""
        self.handoff.client_interests = {'services': ['Masaje', 'Facial']}
        self.handoff.save()

        display = self.admin.client_interests_display(self.handoff)

        self.assertIn('"services"', display)
        self.assertIn('Masaje', display)

    def test_response_time_display_not_assigned(self):
        """response_time_display debe mostrar 'Sin asignar'"""
        display = self.admin.response_time_display(self.handoff)
        self.assertEqual(display, "Sin asignar")

    def test_response_time_display_assigned(self):
        """response_time_display debe mostrar minutos"""
        self.handoff.assigned_at = self.handoff.created_at + timedelta(minutes=30)
        self.handoff.save()

        display = self.admin.response_time_display(self.handoff)
        self.assertEqual(display, "30 minutos")

    def test_resolution_time_display_not_resolved(self):
        """resolution_time_display debe mostrar 'Sin resolver'"""
        display = self.admin.resolution_time_display(self.handoff)
        self.assertEqual(display, "Sin resolver")

    def test_resolution_time_display_resolved(self):
        """resolution_time_display debe mostrar minutos"""
        self.handoff.resolved_at = self.handoff.created_at + timedelta(hours=2)
        self.handoff.save()

        display = self.admin.resolution_time_display(self.handoff)
        self.assertEqual(display, "120 minutos")

    def test_assign_to_me_action_pending(self):
        """assign_to_me debe asignar handoffs PENDING"""
        request = MockRequest(self.staff_user)
        request._messages = Mock()  # Mock para messages framework

        queryset = HumanHandoffRequest.objects.filter(pk=self.handoff.pk)
        self.admin.assign_to_me(request, queryset)

        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.assigned_to, self.staff_user)
        self.assertEqual(self.handoff.status, HumanHandoffRequest.Status.ASSIGNED)
        self.assertIsNotNone(self.handoff.assigned_at)

    def test_assign_to_me_action_already_assigned(self):
        """assign_to_me NO debe asignar handoffs ya asignados"""
        self.handoff.status = HumanHandoffRequest.Status.ASSIGNED
        self.handoff.assigned_to = self.admin_user
        self.handoff.save()

        request = MockRequest(self.staff_user)
        request._messages = Mock()

        queryset = HumanHandoffRequest.objects.filter(pk=self.handoff.pk)
        self.admin.assign_to_me(request, queryset)

        # No debe cambiar la asignación
        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.assigned_to, self.admin_user)  # Sigue siendo admin

    def test_mark_as_resolved_action(self):
        """mark_as_resolved debe marcar handoffs como resueltos"""
        self.handoff.status = HumanHandoffRequest.Status.ASSIGNED
        self.handoff.assigned_to = self.staff_user
        self.handoff.save()

        request = MockRequest(self.staff_user)
        request._messages = Mock()

        queryset = HumanHandoffRequest.objects.filter(pk=self.handoff.pk)
        self.admin.mark_as_resolved(request, queryset)

        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.status, HumanHandoffRequest.Status.RESOLVED)
        self.assertIsNotNone(self.handoff.resolved_at)

    def test_mark_as_resolved_action_pending_ignored(self):
        """mark_as_resolved NO debe resolver handoffs PENDING"""
        initial_status = self.handoff.status

        request = MockRequest(self.staff_user)
        request._messages = Mock()

        queryset = HumanHandoffRequest.objects.filter(pk=self.handoff.pk)
        self.admin.mark_as_resolved(request, queryset)

        self.handoff.refresh_from_db()
        self.assertEqual(self.handoff.status, initial_status)  # No cambió
        self.assertIsNone(self.handoff.resolved_at)

    def test_has_add_permission(self):
        """Nadie puede crear handoffs manualmente"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission_staff(self):
        """Staff puede cambiar handoffs"""
        request = MockRequest(self.staff_user)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_admin(self):
        """Admin puede cambiar handoffs"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_regular(self):
        """Usuario regular NO puede cambiar handoffs"""
        request = MockRequest(self.regular_user)
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission_admin(self):
        """Admin puede eliminar handoffs"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_staff(self):
        """Staff NO puede eliminar handoffs"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_has_view_permission_staff(self):
        """Staff puede ver handoffs"""
        request = MockRequest(self.staff_user)
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_regular(self):
        """Usuario regular NO puede ver handoffs"""
        request = MockRequest(self.regular_user)
        self.assertFalse(self.admin.has_view_permission(request))


class HumanMessageAdminTest(TestCase):
    """Tests para HumanMessageAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = HumanMessageAdmin(HumanMessage, self.site)

        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password"
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF
        )

        self.client_user = User.objects.create_user(
            phone_number="+4444444444",
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

        self.message_staff = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.staff_user,
            is_from_staff=True,
            message="Hello, how can I help you?"
        )

        self.message_client = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.client_user,
            is_from_staff=False,
            message="I need information about prices"
        )

    def test_direction_display_from_staff(self):
        """direction_display debe mostrar '→ Cliente' para staff"""
        display = self.admin.direction_display(self.message_staff)
        self.assertEqual(display, "→ Cliente")

    def test_direction_display_from_client(self):
        """direction_display debe mostrar '← Cliente' para cliente"""
        display = self.admin.direction_display(self.message_client)
        self.assertEqual(display, "← Cliente")

    def test_message_preview_short(self):
        """message_preview debe mostrar mensaje completo si es corto"""
        short_message = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.staff_user,
            is_from_staff=True,
            message="Short"
        )

        preview = self.admin.message_preview(short_message)
        self.assertEqual(preview, "Short")

    def test_message_preview_long(self):
        """message_preview debe truncar mensajes largos"""
        long_text = "A" * 100
        long_message = HumanMessage.objects.create(
            handoff_request=self.handoff,
            sender=self.staff_user,
            is_from_staff=True,
            message=long_text
        )

        preview = self.admin.message_preview(long_message)
        self.assertEqual(len(preview), 53)  # 50 chars + "..."
        self.assertTrue(preview.endswith("..."))

    def test_has_add_permission(self):
        """Nadie puede crear mensajes manualmente desde admin"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission(self):
        """Nadie puede editar mensajes"""
        request = MockRequest(self.superuser)
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission_admin(self):
        """Admin puede eliminar mensajes"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_has_delete_permission_staff(self):
        """Staff NO puede eliminar mensajes"""
        request = MockRequest(self.staff_user)
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_has_view_permission_staff(self):
        """Staff puede ver mensajes"""
        request = MockRequest(self.staff_user)
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_admin(self):
        """Admin puede ver mensajes"""
        request = MockRequest(self.admin_user)
        self.assertTrue(self.admin.has_view_permission(request))


class IPBlocklistAdminTest(TestCase):
    """Tests para IPBlocklistAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = IPBlocklistAdmin(IPBlocklist, self.site)

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password",
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN,
        )
        self.staff_user = User.objects.create_user(
            phone_number="+3333333333",
            email="staff@example.com",
            first_name="Staff",
            role=User.Role.STAFF,
        )

        self.block = IPBlocklist.objects.create(
            ip_address="1.1.1.1",
            reason=IPBlocklist.BlockReason.ABUSE,
            blocked_by=self.admin_user,
        )

    def test_reason_display(self):
        """reason_display debe incluir la descripción legible."""
        html = self.admin.reason_display(self.block)
        self.assertIn(self.block.get_reason_display(), html)

    def test_blocked_by_display_system(self):
        """blocked_by_display debe mostrar Sistema si no hay usuario."""
        block = IPBlocklist.objects.create(
            ip_address="1.1.1.2", reason=IPBlocklist.BlockReason.SPAM
        )
        self.assertEqual(self.admin.blocked_by_display(block), "Sistema")

    def test_actions_activate_and_deactivate(self):
        """Las acciones deben cambiar el estado is_active."""
        request = MockRequest(self.admin_user)
        request._messages = Mock()
        block = IPBlocklist.objects.create(
            ip_address="1.1.1.3",
            reason=IPBlocklist.BlockReason.MANUAL,
            is_active=False,
        )

        self.admin.activate_blocks(request, IPBlocklist.objects.filter(pk=block.pk))
        block.refresh_from_db()
        self.assertTrue(block.is_active)

        self.admin.deactivate_blocks(request, IPBlocklist.objects.filter(pk=block.pk))
        block.refresh_from_db()
        self.assertFalse(block.is_active)

    def test_save_model_sets_blocked_by(self):
        """save_model debe asignar blocked_by al crear."""
        request = MockRequest(self.superuser)
        block = IPBlocklist(
            ip_address="1.1.1.4", reason=IPBlocklist.BlockReason.FRAUD
        )

        self.admin.save_model(request, block, form=None, change=False)

        self.assertEqual(block.blocked_by, self.superuser)

    def test_permissions(self):
        """Permisos de agregar/cambiar/ver dependen del rol."""
        admin_request = MockRequest(self.admin_user)
        staff_request = MockRequest(self.staff_user)

        self.assertTrue(self.admin.has_add_permission(admin_request))
        self.assertTrue(self.admin.has_change_permission(admin_request))
        self.assertTrue(self.admin.has_delete_permission(admin_request))
        self.assertTrue(self.admin.has_view_permission(admin_request))

        self.assertFalse(self.admin.has_add_permission(staff_request))
        self.assertFalse(self.admin.has_change_permission(staff_request))
        self.assertFalse(self.admin.has_delete_permission(staff_request))
        self.assertTrue(self.admin.has_view_permission(staff_request))


class SuspiciousActivityAdminTest(TestCase):
    """Tests para SuspiciousActivityAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.admin = SuspiciousActivityAdmin(SuspiciousActivity, self.site)

        self.superuser = User.objects.create_superuser(
            phone_number="+1111111111",
            email="super@example.com",
            first_name="Super",
            password="password",
        )
        self.admin_user = User.objects.create_user(
            phone_number="+2222222222",
            email="admin@example.com",
            first_name="Admin",
            role=User.Role.ADMIN,
        )
        self.anon_user = AnonymousUser.objects.create(ip_address="5.5.5.5", name="Anon")
        self.activity = SuspiciousActivity.objects.create(
            anonymous_user=self.anon_user,
            ip_address="5.5.5.5",
            activity_type=SuspiciousActivity.ActivityType.JAILBREAK_ATTEMPT,
            severity=SuspiciousActivity.SeverityLevel.HIGH,
            description="Test",
        )

    def test_displays(self):
        """Displays deben incluir la información de actividad y severidad."""
        self.assertIn("Jailbreak", self.admin.activity_type_display(self.activity))
        self.assertIn("Pendiente", self.admin.reviewed_display(self.activity))

    def test_mark_as_reviewed_and_unreviewed(self):
        """Acciones personalizadas deben actualizar estados de revisión."""
        request = MockRequest(self.admin_user)
        request._messages = Mock()

        self.admin.mark_as_reviewed(request, SuspiciousActivity.objects.all())
        self.activity.refresh_from_db()
        self.assertTrue(self.activity.reviewed)
        self.assertEqual(self.activity.reviewed_by, self.admin_user)

        self.admin.mark_as_unreviewed(request, SuspiciousActivity.objects.all())
        self.activity.refresh_from_db()
        self.assertFalse(self.activity.reviewed)
        self.assertIsNone(self.activity.reviewed_by)

    def test_changelist_view_extra_context(self):
        """changelist_view debe agregar estadísticas al contexto."""
        SuspiciousActivity.objects.create(
            anonymous_user=self.anon_user,
            ip_address="6.6.6.6",
            activity_type=SuspiciousActivity.ActivityType.OFF_TOPIC_SPAM,
            severity=SuspiciousActivity.SeverityLevel.MEDIUM,
            description="Otro",
        )
        request = RequestFactory().get("/admin/bot/suspiciousactivity/")
        request.user = self.superuser

        with patch(
            "bot.admin.admin.ModelAdmin.changelist_view", return_value=HttpResponse("ok")
        ) as mocked_super:
            response = self.admin.changelist_view(request)

        self.assertEqual(response.content, b"ok")
        extra = mocked_super.call_args.kwargs["extra_context"]
        self.assertIn("activities_by_type", extra)
        self.assertIn("top_suspicious_ips", extra)
