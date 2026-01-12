"""
Tests de sad paths y edge cases para el sistema de usuarios anónimos.
"""
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from datetime import timedelta
import uuid

from bot.models import AnonymousUser, BotConversationLog, BotConfiguration

User = get_user_model()


class AnonymousUserExpirationTest(TestCase):
    """Tests para manejo de sesiones expiradas"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_is_expired_before_expiration(self):
        """Sesión no debe estar expirada antes de la fecha límite"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Debe expirar en 30 días (default)
        self.assertFalse(anon_user.is_expired)
        self.assertGreater(anon_user.expires_at, timezone.now())

    def test_is_expired_after_expiration(self):
        """Sesión debe estar expirada después de la fecha límite"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Forzar expiración
        anon_user.expires_at = timezone.now() - timedelta(days=1)
        anon_user.save()

        self.assertTrue(anon_user.is_expired)

    def test_expiration_date_auto_set(self):
        """expires_at debe establecerse automáticamente en creación"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Debe estar a ~30 días en el futuro
        delta = anon_user.expires_at - timezone.now()
        self.assertAlmostEqual(delta.days, 30, delta=1)

    def test_expired_session_not_converted(self):
        """Sesión expirada sin conversión debe ser elegible para limpieza"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )
        anon_user.expires_at = timezone.now() - timedelta(days=1)
        anon_user.save()

        # Verificar condiciones para cleanup
        self.assertTrue(anon_user.is_expired)
        self.assertIsNone(anon_user.converted_to_user)

        # Debe ser eliminable por cleanup task
        cleanup_query = AnonymousUser.objects.filter(
            expires_at__lt=timezone.now(),
            converted_to_user__isnull=True
        )
        self.assertIn(anon_user, cleanup_query)

    def test_expired_session_converted_preserved(self):
        """Sesión expirada pero convertida NO debe limpiarse"""
        user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test"
        )

        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            converted_to_user=user
        )
        anon_user.expires_at = timezone.now() - timedelta(days=1)
        anon_user.save()

        # No debe aparecer en cleanup query
        cleanup_query = AnonymousUser.objects.filter(
            expires_at__lt=timezone.now(),
            converted_to_user__isnull=True
        )
        self.assertNotIn(anon_user, cleanup_query)


class AnonymousUserConversionTest(TestCase):
    """Tests para conversión de usuarios anónimos a registrados"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_convert_anonymous_to_registered(self):
        """Debe poder convertir usuario anónimo a registrado"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="John Doe",
            email="john@example.com"
        )

        # Crear usuario registrado
        user = User.objects.create_user(
            phone_number="+1234567890",
            email="john@example.com",
            first_name="John",
            last_name="Doe"
        )

        # Marcar conversión
        anon_user.converted_to_user = user
        anon_user.save()

        # Verificar conversión
        self.assertIsNotNone(anon_user.converted_to_user)
        self.assertEqual(anon_user.converted_to_user, user)

    def test_conversation_logs_preserved_after_conversion(self):
        """Logs de conversación deben preservarse después de conversión"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Crear logs para el usuario anónimo
        log1 = BotConversationLog.objects.create(
            anonymous_user=anon_user,
            message="Hola",
            response="Bienvenido",
            tokens_used=50
        )
        log2 = BotConversationLog.objects.create(
            anonymous_user=anon_user,
            message="Precios",
            response="Aquí están los precios",
            tokens_used=75
        )

        # Convertir
        user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test"
        )
        anon_user.converted_to_user = user
        anon_user.save()

        # Los logs deben seguir existiendo
        self.assertEqual(BotConversationLog.objects.filter(anonymous_user=anon_user).count(), 2)

    def test_multiple_anonymous_sessions_same_user(self):
        """Mismo usuario puede tener múltiples sesiones anónimas"""
        user = User.objects.create_user(
            phone_number="+1234567890",
            email="test@example.com",
            first_name="Test"
        )

        # Crear múltiples sesiones anónimas convertidas al mismo usuario
        anon1 = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            converted_to_user=user
        )
        anon2 = AnonymousUser.objects.create(
            ip_address="192.168.1.1",
            converted_to_user=user
        )

        # Ambas deben estar vinculadas al mismo usuario
        self.assertEqual(anon1.converted_to_user, user)
        self.assertEqual(anon2.converted_to_user, user)
        self.assertEqual(user.converted_anonymous_users.count(), 2)


class AnonymousUserDisplayNameTest(TestCase):
    """Tests para la propiedad display_name"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_display_name_with_name(self):
        """display_name debe usar el nombre si está disponible"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name="María García"
        )

        self.assertEqual(anon_user.display_name, "María García")

    def test_display_name_without_name(self):
        """display_name debe usar session_id truncado si no hay nombre"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Debe contener "Visitante" y primeros caracteres del UUID
        self.assertIn("Visitante", anon_user.display_name)
        self.assertIn(str(anon_user.session_id)[:8], anon_user.display_name)

    def test_display_name_empty_string_name(self):
        """display_name debe manejar nombre como string vacío"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            name=""
        )

        # Debe usar formato de visitante
        self.assertIn("Visitante", anon_user.display_name)


class AnonymousUserValidationTest(TestCase):
    """Tests de validación de modelo AnonymousUser"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_session_id_is_uuid(self):
        """session_id debe ser un UUID válido"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Debe ser UUID válido
        self.assertIsInstance(anon_user.session_id, uuid.UUID)

    def test_session_id_unique(self):
        """session_id debe ser único"""
        anon1 = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        # Intentar crear otro con mismo session_id debe fallar
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            AnonymousUser.objects.create(
                ip_address="192.168.1.1",
                session_id=anon1.session_id  # Mismo UUID
            )

    def test_ip_address_required(self):
        """ip_address es campo requerido"""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            AnonymousUser.objects.create()  # Sin IP

    def test_email_format_validation(self):
        """Email debe tener formato válido si se proporciona"""
        # Email válido debe funcionar
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            email="valid@example.com"
        )
        anon_user.full_clean()  # No debe lanzar excepción

    def test_invalid_email_format_rejected(self):
        """Email con formato inválido debe ser rechazado"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1",
            email="not-an-email"
        )

        # full_clean debe detectar email inválido
        with self.assertRaises(ValidationError):
            anon_user.full_clean()


class AnonymousUserLastActivityTest(TestCase):
    """Tests para tracking de última actividad"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_last_activity_auto_updates(self):
        """last_activity debe actualizarse automáticamente en save()"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        initial_activity = anon_user.last_activity

        # Esperar un momento y guardar de nuevo
        import time
        time.sleep(0.1)

        anon_user.save()
        anon_user.refresh_from_db()

        # last_activity debe haberse actualizado
        self.assertGreater(anon_user.last_activity, initial_activity)

    def test_last_activity_set_on_creation(self):
        """last_activity debe establecerse en creación"""
        anon_user = AnonymousUser.objects.create(
            ip_address="127.0.0.1"
        )

        self.assertIsNotNone(anon_user.last_activity)
        self.assertLessEqual(anon_user.last_activity, timezone.now())


class AnonymousUserQueryTest(TestCase):
    """Tests para queries y filtros de AnonymousUser"""

    def setUp(self):
        self.config = BotConfiguration.objects.create(
            site_name="Test Spa",
            booking_url="http://example.com/book"
        )

    def test_ordering_by_last_activity(self):
        """Usuarios deben ordenarse por última actividad (más reciente primero)"""
        # Crear usuarios con diferentes actividades
        anon1 = AnonymousUser.objects.create(ip_address="1.1.1.1")

        import time
        time.sleep(0.1)

        anon2 = AnonymousUser.objects.create(ip_address="2.2.2.2")

        time.sleep(0.1)

        anon3 = AnonymousUser.objects.create(ip_address="3.3.3.3")

        # Query debe retornar en orden de actividad descendente
        users = list(AnonymousUser.objects.all())

        self.assertEqual(users[0], anon3)  # Más reciente
        self.assertEqual(users[1], anon2)
        self.assertEqual(users[2], anon1)  # Más antiguo

    def test_filter_by_ip(self):
        """Debe poder filtrar por IP"""
        anon1 = AnonymousUser.objects.create(ip_address="1.1.1.1")
        anon2 = AnonymousUser.objects.create(ip_address="2.2.2.2")

        result = AnonymousUser.objects.filter(ip_address="1.1.1.1")

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), anon1)

    def test_filter_expired_sessions(self):
        """Debe poder filtrar sesiones expiradas"""
        # Sesión válida
        anon_valid = AnonymousUser.objects.create(ip_address="1.1.1.1")

        # Sesión expirada
        anon_expired = AnonymousUser.objects.create(ip_address="2.2.2.2")
        anon_expired.expires_at = timezone.now() - timedelta(days=1)
        anon_expired.save()

        # Query de sesiones expiradas
        expired = AnonymousUser.objects.filter(expires_at__lt=timezone.now())

        self.assertIn(anon_expired, expired)
        self.assertNotIn(anon_valid, expired)
