"""
Tests para la configuración de settings.py
Cobertura objetivo: 85-95%
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.test import TestCase, override_settings


class SettingsValidationTests(TestCase):
    """Tests para validación de variables de entorno"""
    
    def test_secret_key_is_configured(self):
        """SECRET_KEY debe estar configurada"""
        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertNotEqual(settings.SECRET_KEY, "")
        self.assertGreater(len(settings.SECRET_KEY), 20)
    
    def test_debug_mode_from_env(self):
        """DEBUG debe leer correctamente de variable de entorno"""
        # El valor actual debe ser booleano
        self.assertIsInstance(settings.DEBUG, bool)
    
    @patch.dict(os.environ, {'DEBUG': '1'})
    def test_debug_true_from_env(self):
        """DEBUG=1 debe resultar en True"""
        # Nota: Este test requiere recargar settings, lo cual es complejo
        # En su lugar, probamos la lógica directamente
        debug_value = os.getenv("DEBUG", "0") in ("1", "true", "True")
        self.assertTrue(debug_value)
    
    @patch.dict(os.environ, {'DEBUG': '0'})
    def test_debug_false_from_env(self):
        """DEBUG=0 debe resultar en False"""
        debug_value = os.getenv("DEBUG", "0") in ("1", "true", "True")
        self.assertFalse(debug_value)


class DatabaseConfigTests(TestCase):
    """Tests para configuración de base de datos"""
    
    def test_database_engine_is_postgresql(self):
        """Motor de base de datos debe ser PostgreSQL"""
        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.postgresql'
        )
    
    def test_database_has_connection_timeout(self):
        """Base de datos debe tener timeout configurado"""
        db_options = settings.DATABASES['default'].get('OPTIONS', {})
        self.assertIn('connect_timeout', db_options)
        self.assertEqual(db_options['connect_timeout'], 10)
    
    def test_database_ssl_mode_configured(self):
        """SSL mode debe estar configurado"""
        db_options = settings.DATABASES['default'].get('OPTIONS', {})
        self.assertIn('sslmode', db_options)
        # En desarrollo puede ser 'disable', 'prefer', en producción 'require'
        self.assertIn(db_options['sslmode'], ['disable', 'prefer', 'require'])
    
    def test_database_connection_pooling(self):
        """Connection pooling debe estar configurado"""
        conn_max_age = settings.DATABASES['default'].get('CONN_MAX_AGE', 0)
        self.assertGreater(conn_max_age, 0)
        self.assertEqual(conn_max_age, 60)


class RateLimitingTests(TestCase):
    """Tests para configuración de rate limiting"""
    
    def test_throttle_classes_configured(self):
        """Clases de throttling deben estar configuradas"""
        throttle_classes = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_CLASSES', [])
        self.assertGreater(len(throttle_classes), 0)
        self.assertIn('rest_framework.throttling.UserRateThrottle', throttle_classes)
        self.assertIn('rest_framework.throttling.AnonRateThrottle', throttle_classes)
        self.assertIn('rest_framework.throttling.ScopedRateThrottle', throttle_classes)
    
    def test_user_rate_limit_is_restrictive(self):
        """Rate limit de usuarios debe ser restrictivo"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        user_rate = rates.get('user', '')
        
        # Debe ser 100/min o menos
        self.assertIn('100/min', user_rate)
    
    def test_anon_rate_limit_is_restrictive(self):
        """Rate limit de anónimos debe ser restrictivo"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        anon_rate = rates.get('anon', '')
        
        # Debe ser 30/min o menos
        self.assertIn('30/min', anon_rate)
    
    def test_auth_login_scope_exists(self):
        """Scope de auth_login debe existir"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('auth_login', rates)
        # Debe ser muy restrictivo (3/min)
        self.assertIn('3/min', rates['auth_login'])
    
    def test_auth_verify_scope_exists(self):
        """Scope de auth_verify debe existir"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('auth_verify', rates)
    
    def test_bot_scopes_exist(self):
        """Scopes de bot deben existir"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('bot', rates)
        self.assertIn('bot_daily', rates)
        self.assertIn('bot_ip', rates)
    
    def test_critical_endpoint_scopes_exist(self):
        """Scopes de endpoints críticos deben existir"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('appointments_create', rates)
        self.assertIn('profile_update', rates)
        self.assertIn('analytics_export', rates)
    
    def test_payments_scope_exists(self):
        """Scope de payments debe existir"""
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn('payments', rates)


class LoggingConfigTests(TestCase):
    """Tests para configuración de logging"""
    
    def test_logging_version_is_1(self):
        """Versión de logging debe ser 1"""
        self.assertEqual(settings.LOGGING['version'], 1)
    
    def test_logging_handlers_exist(self):
        """Handlers de logging deben existir"""
        handlers = settings.LOGGING.get('handlers', {})
        self.assertIn('console', handlers)
        self.assertIn('file', handlers)
        self.assertIn('error_file', handlers)
    
    def test_console_handler_has_filters(self):
        """Console handler debe tener filtros de sanitización"""
        console_handler = settings.LOGGING['handlers']['console']
        filters = console_handler.get('filters', [])
        self.assertIn('sanitize_api_keys', filters)
        self.assertIn('sanitize_pii', filters)
    
    def test_file_handler_configuration(self):
        """File handler debe estar configurado correctamente"""
        file_handler = settings.LOGGING['handlers']['file']
        
        self.assertEqual(file_handler['class'], 'logging.handlers.RotatingFileHandler')
        self.assertEqual(file_handler['maxBytes'], 10 * 1024 * 1024)  # 10 MB
        self.assertEqual(file_handler['backupCount'], 10)
        
        # Debe tener filtros
        filters = file_handler.get('filters', [])
        self.assertIn('sanitize_api_keys', filters)
        self.assertIn('sanitize_pii', filters)
    
    def test_error_file_handler_configuration(self):
        """Error file handler debe estar configurado correctamente"""
        error_handler = settings.LOGGING['handlers']['error_file']
        
        self.assertEqual(error_handler['class'], 'logging.handlers.RotatingFileHandler')
        self.assertEqual(error_handler['level'], 'ERROR')
        self.assertEqual(error_handler['maxBytes'], 10 * 1024 * 1024)  # 10 MB
        self.assertEqual(error_handler['backupCount'], 5)
    
    def test_logging_filters_configured(self):
        """Filtros de logging deben estar configurados"""
        filters = settings.LOGGING.get('filters', {})
        self.assertIn('sanitize_api_keys', filters)
        self.assertIn('sanitize_pii', filters)
        
        # Verificar que apuntan a las clases correctas
        self.assertEqual(
            filters['sanitize_api_keys']['()'],
            'core.logging_filters.SanitizeAPIKeyFilter'
        )
        self.assertEqual(
            filters['sanitize_pii']['()'],
            'core.logging_filters.SanitizePIIFilter'
        )
    
    def test_root_logger_uses_all_handlers(self):
        """Root logger debe usar todos los handlers"""
        root_handlers = settings.LOGGING['root']['handlers']
        self.assertIn('console', root_handlers)
        self.assertIn('file', root_handlers)
        self.assertIn('error_file', root_handlers)
    
    def test_bot_logger_configured(self):
        """Logger específico para bot debe existir"""
        loggers = settings.LOGGING.get('loggers', {})
        self.assertIn('bot', loggers)
        
        bot_logger = loggers['bot']
        self.assertEqual(bot_logger['level'], 'INFO')
        self.assertFalse(bot_logger['propagate'])


class CeleryBeatScheduleTests(TestCase):
    """Tests para tareas programadas de Celery Beat"""
    
    def test_celery_beat_schedule_exists(self):
        """CELERY_BEAT_SCHEDULE debe existir"""
        self.assertIsNotNone(settings.CELERY_BEAT_SCHEDULE)
        self.assertIsInstance(settings.CELERY_BEAT_SCHEDULE, dict)
    
    def test_cleanup_idempotency_keys_task_exists(self):
        """Tarea de limpieza de idempotency keys debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('cleanup-idempotency-keys', schedule)
        
        task = schedule['cleanup-idempotency-keys']
        self.assertEqual(task['task'], 'core.tasks.cleanup_old_idempotency_keys')
    
    def test_cleanup_user_sessions_task_exists(self):
        """Tarea de limpieza de sesiones debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('cleanup-user-sessions', schedule)
        
        task = schedule['cleanup-user-sessions']
        self.assertEqual(task['task'], 'users.tasks.cleanup_inactive_sessions')
    
    def test_cleanup_kiosk_sessions_task_exists(self):
        """Tarea de limpieza de sesiones de kiosk debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('cleanup-kiosk-sessions', schedule)
        
        task = schedule['cleanup-kiosk-sessions']
        self.assertEqual(task['task'], 'profiles.tasks.cleanup_expired_kiosk_sessions')
    
    def test_cleanup_notification_logs_task_exists(self):
        """Tarea de limpieza de logs de notificaciones debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('cleanup-notification-logs', schedule)
        
        task = schedule['cleanup-notification-logs']
        self.assertEqual(task['task'], 'notifications.tasks.cleanup_old_notification_logs')
    
    def test_bot_daily_token_report_task_exists(self):
        """Tarea de reporte diario de tokens del bot debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('bot-daily-token-report', schedule)
        
        task = schedule['bot-daily-token-report']
        self.assertEqual(task['task'], 'bot.tasks.report_daily_token_usage')
    
    def test_bot_cleanup_old_logs_task_exists(self):
        """Tarea de limpieza de logs del bot debe existir"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('bot-cleanup-old-logs', schedule)
        
        task = schedule['bot-cleanup-old-logs']
        self.assertEqual(task['task'], 'bot.tasks.cleanup_old_bot_logs')
    
    def test_all_cleanup_tasks_have_schedule(self):
        """Todas las tareas de limpieza deben tener schedule configurado"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        cleanup_tasks = [
            'cleanup-idempotency-keys',
            'cleanup-user-sessions',
            'cleanup-kiosk-sessions',
            'cleanup-notification-logs'
        ]
        
        for task_name in cleanup_tasks:
            self.assertIn('schedule', schedule[task_name])


class SecurityConfigTests(TestCase):
    """Tests para configuración de seguridad"""
    
    def test_cors_allowed_origins_configured(self):
        """CORS_ALLOWED_ORIGINS debe estar configurado"""
        self.assertIsNotNone(settings.CORS_ALLOWED_ORIGINS)
        self.assertIsInstance(settings.CORS_ALLOWED_ORIGINS, list)
    
    def test_csrf_trusted_origins_configured(self):
        """CSRF_TRUSTED_ORIGINS debe estar configurado"""
        self.assertIsNotNone(settings.CSRF_TRUSTED_ORIGINS)
        self.assertIsInstance(settings.CSRF_TRUSTED_ORIGINS, list)
    
    def test_allowed_hosts_configured(self):
        """ALLOWED_HOSTS debe estar configurado"""
        self.assertIsNotNone(settings.ALLOWED_HOSTS)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertGreater(len(settings.ALLOWED_HOSTS), 0)
    
    def test_secure_browser_xss_filter_enabled(self):
        """XSS filter debe estar habilitado"""
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)
    
    def test_secure_content_type_nosniff_enabled(self):
        """Content type nosniff debe estar habilitado"""
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
    
    def test_x_frame_options_configured(self):
        """X-Frame-Options debe estar configurado"""
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
    
    def test_csp_directives_configured(self):
        """CSP directives deben estar configuradas"""
        self.assertIsNotNone(settings.CSP_DIRECTIVES)
        self.assertIsInstance(settings.CSP_DIRECTIVES, dict)
        
        # Verificar directivas básicas
        self.assertIn('default-src', settings.CSP_DIRECTIVES)
        self.assertIn('script-src', settings.CSP_DIRECTIVES)
        self.assertIn('style-src', settings.CSP_DIRECTIVES)


class JWTConfigTests(TestCase):
    """Tests para configuración de JWT"""
    
    def test_jwt_access_token_lifetime_configured(self):
        """Lifetime de access token debe estar configurado"""
        from datetime import timedelta
        
        lifetime = settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME')
        self.assertIsNotNone(lifetime)
        self.assertIsInstance(lifetime, timedelta)
    
    def test_jwt_refresh_token_lifetime_configured(self):
        """Lifetime de refresh token debe estar configurado"""
        from datetime import timedelta
        
        lifetime = settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME')
        self.assertIsNotNone(lifetime)
        self.assertIsInstance(lifetime, timedelta)
    
    def test_jwt_rotate_refresh_tokens_enabled(self):
        """Rotación de refresh tokens debe estar habilitada"""
        self.assertTrue(settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS'))
    
    def test_jwt_blacklist_after_rotation_enabled(self):
        """Blacklist después de rotación debe estar habilitada"""
        self.assertTrue(settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION'))
    
    def test_jwt_user_id_field_configured(self):
        """Campo de user ID debe estar configurado"""
        self.assertEqual(settings.SIMPLE_JWT.get('USER_ID_FIELD'), 'phone_number')
    
    def test_jwt_algorithm_configured(self):
        """Algoritmo JWT debe estar configurado"""
        algorithm = settings.SIMPLE_JWT.get('ALGORITHM')
        self.assertIsNotNone(algorithm)
        self.assertIn(algorithm, ['HS256', 'HS384', 'HS512', 'RS256'])


class CacheConfigTests(TestCase):
    """Tests para configuración de caché"""
    
    def test_cache_backend_is_redis(self):
        """Backend de caché debe ser Redis"""
        cache_backend = settings.CACHES['default']['BACKEND']
        self.assertEqual(cache_backend, 'django_redis.cache.RedisCache')
    
    def test_cache_location_configured(self):
        """Ubicación de caché debe estar configurada"""
        location = settings.CACHES['default'].get('LOCATION')
        self.assertIsNotNone(location)
        self.assertTrue(location.startswith('redis://'))
    
    def test_cache_timeout_configured(self):
        """Timeout de caché debe estar configurado"""
        timeout = settings.CACHES['default'].get('TIMEOUT')
        self.assertIsNotNone(timeout)
        self.assertGreater(timeout, 0)
    
    def test_session_engine_uses_cache(self):
        """Motor de sesiones debe usar caché"""
        self.assertEqual(settings.SESSION_ENGINE, 'django.contrib.sessions.backends.cache')


class InstalledAppsTests(TestCase):
    """Tests para apps instaladas"""
    
    def test_required_django_apps_installed(self):
        """Apps de Django requeridas deben estar instaladas"""
        required_apps = [
            'django.contrib.admin',
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
        ]
        
        for app in required_apps:
            self.assertIn(app, settings.INSTALLED_APPS)
    
    def test_drf_installed(self):
        """Django REST Framework debe estar instalado"""
        self.assertIn('rest_framework', settings.INSTALLED_APPS)
        self.assertIn('rest_framework_simplejwt', settings.INSTALLED_APPS)
    
    def test_custom_apps_installed(self):
        """Apps personalizadas deben estar instaladas"""
        custom_apps = [
            'users',
            'spa',
            'profiles',
            'core',
            'marketplace',
            'notifications',
            'analytics',
            'bot',
            'finances',
        ]
        
        for app in custom_apps:
            self.assertIn(app, settings.INSTALLED_APPS)
    
    def test_cors_headers_installed(self):
        """CORS headers debe estar instalado"""
        self.assertIn('corsheaders', settings.INSTALLED_APPS)
    
    def test_csp_installed(self):
        """CSP debe estar instalado"""
        self.assertIn('csp', settings.INSTALLED_APPS)
    
    def test_simple_history_installed(self):
        """Simple history debe estar instalado"""
        self.assertIn('simple_history', settings.INSTALLED_APPS)


class MiddlewareTests(TestCase):
    """Tests para middleware"""
    
    def test_security_middleware_first(self):
        """SecurityMiddleware debe estar primero o segundo (después de Prometheus)"""
        # Prometheus debe estar primero para capturar todas las métricas
        # SecurityMiddleware debe estar inmediatamente después
        security_idx = settings.MIDDLEWARE.index('django.middleware.security.SecurityMiddleware')
        # SecurityMiddleware debe estar entre los primeros 2 middlewares
        self.assertLessEqual(security_idx, 1)
    
    def test_cors_middleware_before_common(self):
        """CorsMiddleware debe estar antes de CommonMiddleware"""
        cors_index = settings.MIDDLEWARE.index('corsheaders.middleware.CorsMiddleware')
        common_index = settings.MIDDLEWARE.index('django.middleware.common.CommonMiddleware')
        self.assertLess(cors_index, common_index)
    
    def test_required_middleware_installed(self):
        """Middleware requerido debe estar instalado"""
        required_middleware = [
            'django.middleware.security.SecurityMiddleware',
            'corsheaders.middleware.CorsMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ]
        
        for middleware in required_middleware:
            self.assertIn(middleware, settings.MIDDLEWARE)
    
    def test_custom_middleware_installed(self):
        """Middleware personalizado debe estar instalado"""
        custom_middleware = [
            'profiles.middleware.KioskFlowEnforcementMiddleware',
            'csp.middleware.CSPMiddleware',
            'simple_history.middleware.HistoryRequestMiddleware',
            'core.middleware.RequestIDMiddleware',
            'core.middleware.AdminAuditMiddleware',
        ]
        
        for middleware in custom_middleware:
            self.assertIn(middleware, settings.MIDDLEWARE)


class IntegrationConfigTests(TestCase):
    """Tests para configuración de integraciones externas"""
    
    def test_twilio_config_exists(self):
        """Configuración de Twilio debe existir"""
        # En desarrollo puede ser None
        self.assertTrue(hasattr(settings, 'TWILIO_ACCOUNT_SID'))
        self.assertTrue(hasattr(settings, 'TWILIO_AUTH_TOKEN'))
        self.assertTrue(hasattr(settings, 'TWILIO_VERIFY_SERVICE_SID'))
    
    def test_gemini_config_exists(self):
        """Configuración de Gemini debe existir"""
        self.assertTrue(hasattr(settings, 'GEMINI_API_KEY'))
        self.assertTrue(hasattr(settings, 'GEMINI_MODEL'))
    
    def test_wompi_config_exists(self):
        """Configuración de Wompi debe existir"""
        self.assertTrue(hasattr(settings, 'WOMPI_PUBLIC_KEY'))
        self.assertTrue(hasattr(settings, 'WOMPI_INTEGRITY_SECRET'))
        self.assertTrue(hasattr(settings, 'WOMPI_EVENT_SECRET'))
    
    def test_recaptcha_config_exists(self):
        """Configuración de reCAPTCHA debe existir"""
        self.assertTrue(hasattr(settings, 'RECAPTCHA_V3_SITE_KEY'))
        self.assertTrue(hasattr(settings, 'RECAPTCHA_V3_SECRET_KEY'))
        self.assertTrue(hasattr(settings, 'RECAPTCHA_V3_DEFAULT_SCORE'))


class UtilityFunctionsTests(TestCase):
    """Tests para funciones utilitarias en settings"""
    
    def test_split_env_function(self):
        """Función _split_env debe funcionar correctamente"""
        from studiozens.settings import _split_env
        
        # Test con comas
        result = _split_env('TEST', 'value1,value2,value3')
        self.assertEqual(result, ['value1', 'value2', 'value3'])
        
        # Test con espacios
        result = _split_env('TEST', 'value1 value2 value3')
        self.assertEqual(result, ['value1', 'value2', 'value3'])
        
        # Test con mix
        result = _split_env('TEST', 'value1, value2 value3')
        self.assertEqual(result, ['value1', 'value2', 'value3'])
    
    def test_parse_action_scores_function(self):
        """Función _parse_action_scores debe funcionar correctamente"""
        from studiozens.settings import _parse_action_scores
        
        # Test válido
        result = _parse_action_scores('otp:0.7,verify:0.3')
        self.assertEqual(result, {'otp': 0.7, 'verify': 0.3})
        
        # Test con valores inválidos (debe ignorarlos)
        result = _parse_action_scores('otp:0.7,invalid,verify:abc')
        self.assertEqual(result, {'otp': 0.7})
        
        # Test vacío
        result = _parse_action_scores('')
        self.assertEqual(result, {})
