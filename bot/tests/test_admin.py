import pytest
from bot.admin import BotConfigurationAdmin, BotConversationLogAdmin
from bot.models import BotConfiguration, BotConversationLog
from django.contrib.admin.sites import AdminSite

# Helper simple para simular un request con usuario
class MockRequest:
    def __init__(self, user):
        self.user = user

@pytest.mark.django_db
class TestAdminPermissions:
    
    def setup_method(self):
        self.site = AdminSite()
    
    def test_config_permissions(self):
        admin = BotConfigurationAdmin(BotConfiguration, self.site)
        
        # Simulamos un Superuser (debe tener permiso)
        superuser = MockRequest(type('User', (), {'is_superuser': True, 'role': 'ADMIN'}))
        assert admin.has_change_permission(superuser) is True
        
        # Simulamos Staff normal (NO debe tener permiso)
        staff = MockRequest(type('User', (), {'is_superuser': False, 'role': 'STAFF'}))
        assert admin.has_change_permission(staff) is False
        assert admin.has_delete_permission(staff) is False

    def test_logs_readonly(self):
        """Los logs deben ser inmutables para todos."""
        admin = BotConversationLogAdmin(BotConversationLog, self.site)
        superuser = MockRequest(type('User', (), {'is_superuser': True}))
        
        # Nadie puede crear ni editar logs desde admin
        assert admin.has_add_permission(superuser) is False
        assert admin.has_change_permission(superuser) is False
        # Solo borrar
        assert admin.has_delete_permission(superuser) is True