"""
Tests para el módulo core.
Cubre: GlobalSettings, SoftDeleteModel, IdempotencyKey, AuditLog, Permissions, Decorators.
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError
from unittest.mock import patch, MagicMock
from datetime import timedelta
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response
from rest_framework import status

from core.models import GlobalSettings, AuditLog, IdempotencyKey
from core.utils.decorators import idempotent_view
from core.utils import get_client_ip
from core.api.permissions import RoleAllowed, IsAdmin, IsStaff
from core.tasks import cleanup_old_idempotency_keys
from core.utils.caching import CacheKeys


@pytest.mark.django_db
class TestGlobalSettings:
    """Tests para GlobalSettings singleton"""
    
    def test_load_creates_singleton(self):
        """load() debe crear singleton si no existe"""
        cache.clear()
        GlobalSettings.objects.all().delete()
        
        settings = GlobalSettings.load()
        assert str(settings.id) == "00000000-0000-0000-0000-000000000001"
        assert settings.advance_payment_percentage == 20  # default
    
    def test_load_returns_cached(self):
        """load() debe retornar desde caché si existe"""
        cache.clear()
        GlobalSettings.objects.all().delete()
        
        settings1 = GlobalSettings.load()
        
        # Modificar en DB directamente (sin invalidar caché)
        GlobalSettings.objects.filter(pk=settings1.pk).update(advance_payment_percentage=50)
        
        # Debe retornar desde caché (valor antiguo)
        settings2 = GlobalSettings.load()
        assert settings2.advance_payment_percentage == 20  # cached value
    
    def test_save_invalidates_cache(self):
        """save() debe invalidar caché"""
        cache.clear()
        GlobalSettings.objects.all().delete()
        
        settings = GlobalSettings.load()
        settings.advance_payment_percentage = 25
        settings.save()
        
        # Limpiar instancia local
        cache.delete(CacheKeys.GLOBAL_SETTINGS)
        
        # Debe cargar desde DB con nuevo valor
        fresh = GlobalSettings.load()
        assert fresh.advance_payment_percentage == 25
    
    def test_validation_prevents_invalid_percentage(self):
        """clean() debe prevenir porcentajes > 100"""
        settings = GlobalSettings.load()
        settings.advance_payment_percentage = 150
        
        with pytest.raises(ValidationError) as exc_info:
            settings.clean()
        
        assert "advance_payment_percentage" in exc_info.value.message_dict
    
    def test_validation_prevents_negative_capacity(self):
        """clean() debe prevenir capacidad < 1"""
        settings = GlobalSettings.load()
        settings.low_supervision_capacity = 0
        
        with pytest.raises(ValidationError) as exc_info:
            settings.clean()
        
        assert "low_supervision_capacity" in exc_info.value.message_dict
    
    def test_validation_prevents_invalid_timezone(self):
        """clean() debe prevenir timezone inválido"""
        settings = GlobalSettings.load()
        settings.timezone_display = "Invalid/Timezone"
        
        with pytest.raises(ValidationError) as exc_info:
            settings.clean()
        
        assert "timezone_display" in exc_info.value.message_dict
    
    def test_validation_allows_valid_timezone(self):
        """clean() debe permitir timezone válido"""
        settings = GlobalSettings.load()
        settings.timezone_display = "America/New_York"
        
        # No debe lanzar excepción
        settings.clean()
    
    def test_cannot_decrease_developer_commission(self):
        """No se debe permitir disminuir la comisión del desarrollador"""
        settings = GlobalSettings.load()
        settings.developer_commission_percentage = Decimal("10.00")
        settings.save()
        
        # Intentar disminuir
        settings.developer_commission_percentage = Decimal("5.00")
        
        with pytest.raises(ValidationError) as exc_info:
            settings.clean()
        
        assert "developer_commission_percentage" in exc_info.value.message_dict


@pytest.mark.django_db
class TestIdempotencyKey:
    """Tests para IdempotencyKey"""
    
    def test_create_idempotency_key(self):
        """Debe crear clave de idempotencia correctamente"""
        key = IdempotencyKey.objects.create(
            key="test-key-12345678",
            endpoint="/api/test/",
            status=IdempotencyKey.Status.PENDING
        )
        
        assert key.key == "test-key-12345678"
        assert key.status == IdempotencyKey.Status.PENDING
        assert key.locked_at is None
    
    def test_mark_completed(self):
        """mark_completed() debe actualizar estado correctamente"""
        key = IdempotencyKey.objects.create(
            key="test-key-12345678",
            endpoint="/api/test/",
            status=IdempotencyKey.Status.PENDING
        )
        
        response_data = {"success": True}
        key.mark_completed(response_body=response_data, status_code=200)
        
        assert key.status == IdempotencyKey.Status.COMPLETED
        assert key.response_body == response_data
        assert key.status_code == 200
        assert key.completed_at is not None
    
    def test_cleanup_old_keys(self):
        """cleanup_old_idempotency_keys debe eliminar claves antiguas"""
        # Crear clave completada hace 8 días
        old_key = IdempotencyKey.objects.create(
            key="old-key-12345678",
            endpoint="/api/test/",
            status=IdempotencyKey.Status.COMPLETED,
            completed_at=timezone.now() - timedelta(days=8)
        )
        
        # Crear clave reciente
        recent_key = IdempotencyKey.objects.create(
            key="recent-key-12345678",
            endpoint="/api/test/",
            status=IdempotencyKey.Status.COMPLETED,
            completed_at=timezone.now() - timedelta(days=1)
        )
        
        # Ejecutar limpieza
        result = cleanup_old_idempotency_keys()
        
        # Verificar que solo se eliminó la antigua
        assert not IdempotencyKey.objects.filter(key="old-key-12345678").exists()
        assert IdempotencyKey.objects.filter(key="recent-key-12345678").exists()
        assert result["deleted_completed"] >= 1
    
    def test_cleanup_stale_pending_keys(self):
        """cleanup_old_idempotency_keys debe eliminar claves pendientes antiguas"""
        # Crear clave pendiente hace 25 horas
        stale_key = IdempotencyKey.objects.create(
            key="stale-key-12345678",
            endpoint="/api/test/",
            status=IdempotencyKey.Status.PENDING,
            locked_at=timezone.now() - timedelta(hours=25)
        )
        
        # Ejecutar limpieza
        result = cleanup_old_idempotency_keys()
        
        # Verificar que se eliminó
        assert not IdempotencyKey.objects.filter(key="stale-key-12345678").exists()
        assert result["deleted_stale"] >= 1


@pytest.mark.django_db
class TestAuditLog:
    """Tests para AuditLog"""
    
    def test_audit_log_creation(self, admin_user, client_user):
        """Debe crear log de auditoría correctamente"""
        log = AuditLog.objects.create(
            action=AuditLog.Action.FLAG_NON_GRATA,
            admin_user=admin_user,
            target_user=client_user,
            details="Test details"
        )
        
        assert log.action == AuditLog.Action.FLAG_NON_GRATA
        assert log.admin_user == admin_user
        assert log.target_user == client_user
        assert "Test details" in log.details


@pytest.mark.django_db
class TestPermissions:
    """Tests para permissions"""
    
    def test_role_allowed_validates_valid_roles(self):
        """RoleAllowed debe validar que los roles sean válidos"""
        permission = RoleAllowed()
        
        # Mock request y view
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "CLIENT"
        
        view = MagicMock()
        view.required_roles = {"CLIENT", "INVALID_ROLE"}
        
        # Debe retornar False por rol inválido
        result = permission.has_permission(request, view)
        assert result is False
    
    def test_role_allowed_accepts_valid_roles(self):
        """RoleAllowed debe aceptar roles válidos"""
        permission = RoleAllowed()
        
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "CLIENT"
        
        view = MagicMock()
        view.required_roles = {"CLIENT", "VIP"}
        
        result = permission.has_permission(request, view)
        assert result is True
    
    def test_is_admin_permission(self):
        """IsAdmin debe permitir solo usuarios ADMIN"""
        permission = IsAdmin()
        
        # Usuario ADMIN
        request = MagicMock()
        request.user.role = "ADMIN"
        
        assert permission.has_permission(request, None) is True
        
        # Usuario CLIENT
        request.user.role = "CLIENT"
        assert permission.has_permission(request, None) is False
    
    def test_is_staff_permission(self):
        """IsStaff debe permitir STAFF y ADMIN"""
        permission = IsStaff()
        
        # Usuario STAFF
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "STAFF"
        
        assert permission.has_permission(request, None) is True
        
        # Usuario ADMIN
        request.user.role = "ADMIN"
        assert permission.has_permission(request, None) is True
        
        # Usuario CLIENT
        request.user.role = "CLIENT"
        assert permission.has_permission(request, None) is False


