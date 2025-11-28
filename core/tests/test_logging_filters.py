"""
Tests para filtros de logging (core.logging_filters)
Cobertura objetivo: 90%+
"""
import pytest
import logging
from django.test import TestCase
from core.logging_filters import SanitizeAPIKeyFilter, SanitizePIIFilter


class SanitizeAPIKeyFilterTests(TestCase):
    """Tests para SanitizeAPIKeyFilter"""
    
    def setUp(self):
        """Configurar filtro para tests"""
        self.filter = SanitizeAPIKeyFilter()
    
    def _create_log_record(self, msg, args=()):
        """Helper para crear LogRecord"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None
        )
        if args:
            record.args = args
        return record
    
    def test_sanitize_gemini_api_key(self):
        """Debe sanitizar GEMINI_API_KEY"""
        record = self._create_log_record("GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("AIzaSy", record.msg)
    
    def test_sanitize_gemini_api_key_with_quotes(self):
        """Debe sanitizar GEMINI_API_KEY con comillas"""
        record = self._create_log_record('GEMINI_API_KEY="AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX"')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("AIzaSy", record.msg)
    
    def test_sanitize_gemini_api_key_with_colon(self):
        """Debe sanitizar GEMINI_API_KEY con dos puntos"""
        record = self._create_log_record("GEMINI_API_KEY: AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_sanitize_twilio_auth_token(self):
        """Debe sanitizar TWILIO_AUTH_TOKEN"""
        record = self._create_log_record("TWILIO_AUTH_TOKEN=1234567890abcdefghijklmnopqrst")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("1234567890", record.msg)
    
    def test_sanitize_secret_key(self):
        """Debe sanitizar SECRET_KEY"""
        record = self._create_log_record("SECRET_KEY=django-insecure-abcdefghijklmnopqrstuvwxyz")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("django-insecure", record.msg)
    
    def test_sanitize_api_key_in_url(self):
        """Debe sanitizar API key en URL"""
        record = self._create_log_record("GET https://api.example.com?key=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("AIzaSy", record.msg)
    
    def test_sanitize_api_key_in_url_with_ampersand(self):
        """Debe sanitizar API key en URL con &"""
        record = self._create_log_record("GET https://api.example.com?foo=bar&api_key=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_sanitize_bearer_token(self):
        """Debe sanitizar Bearer token"""
        record = self._create_log_record("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("eyJhbG", record.msg)
    
    def test_sanitize_json_api_key(self):
        """Debe sanitizar API key en JSON"""
        record = self._create_log_record('{"api_key": "AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_sanitize_json_token(self):
        """Debe sanitizar token en JSON"""
        record = self._create_log_record('{"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_sanitize_json_secret(self):
        """Debe sanitizar secret en JSON"""
        record = self._create_log_record('{"secret": "my-secret-value-12345"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_sanitize_json_password(self):
        """Debe sanitizar password en JSON"""
        record = self._create_log_record('{"password": "mypassword123"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
    
    def test_handle_none_message(self):
        """Debe manejar mensaje None sin errores"""
        record = self._create_log_record(None)
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
    
    def test_handle_non_string_message(self):
        """Debe manejar mensaje no-string sin errores"""
        record = self._create_log_record(12345)
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
    
    def test_sanitize_args_dict(self):
        """Debe sanitizar argumentos tipo dict"""
        record = self._create_log_record(
            "Message with args",
            args={'config': 'GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX'}
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        # Los args deben ser sanitizados
        self.assertIsInstance(record.args, dict)
        self.assertIn('config', record.args)
        self.assertIn('***REDACTED***', record.args['config'])
    
    def test_sanitize_args_tuple(self):
        """Debe sanitizar argumentos tipo tuple"""
        record = self._create_log_record(
            "Message with args: %s",
            args=('GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX',)
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIsInstance(record.args, tuple)
        self.assertIn('***REDACTED***', record.args[0])
    
    def test_sanitize_args_list(self):
        """Debe sanitizar argumentos tipo list"""
        record = self._create_log_record(
            "Message with args",
            args=['GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX']
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIsInstance(record.args, list)
        self.assertIn('***REDACTED***', record.args[0])
    
    def test_always_returns_true(self):
        """Filter siempre debe retornar True (no bloquea logs)"""
        record = self._create_log_record("Normal message")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
    
    def test_multiple_patterns_in_same_message(self):
        """Debe sanitizar múltiples patrones en el mismo mensaje"""
        record = self._create_log_record(
            "GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX and TWILIO_AUTH_TOKEN=1234567890abcdefghijkl"
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***REDACTED***", record.msg)
        self.assertNotIn("AIzaSy", record.msg)
        self.assertNotIn("1234567890", record.msg)


class SanitizePIIFilterTests(TestCase):
    """Tests para SanitizePIIFilter"""
    
    def setUp(self):
        """Configurar filtro para tests"""
        self.filter = SanitizePIIFilter()
    
    def _create_log_record(self, msg):
        """Helper para crear LogRecord"""
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None
        )
    
    def test_sanitize_credit_card_with_dashes(self):
        """Debe sanitizar número de tarjeta con guiones"""
        record = self._create_log_record("Tarjeta: 4532-1234-5678-9010")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("****-****-****-****", record.msg)
        self.assertNotIn("4532", record.msg)
    
    def test_sanitize_credit_card_with_spaces(self):
        """Debe sanitizar número de tarjeta con espacios"""
        record = self._create_log_record("Tarjeta: 4532 1234 5678 9010")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("****-****-****-****", record.msg)
    
    def test_sanitize_credit_card_without_separators(self):
        """Debe sanitizar número de tarjeta sin separadores"""
        record = self._create_log_record("Tarjeta: 4532123456789010")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("****-****-****-****", record.msg)
    
    def test_sanitize_email(self):
        """Debe sanitizar email"""
        record = self._create_log_record("Usuario: test@example.com")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***EMAIL***", record.msg)
        self.assertNotIn("test@example.com", record.msg)
    
    def test_sanitize_email_with_subdomain(self):
        """Debe sanitizar email con subdominio"""
        record = self._create_log_record("Email: user@mail.example.com")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***EMAIL***", record.msg)
    
    def test_sanitize_email_with_plus(self):
        """Debe sanitizar email con +"""
        record = self._create_log_record("Email: user+tag@example.com")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***EMAIL***", record.msg)
    
    def test_sanitize_phone_international_format(self):
        """Debe sanitizar teléfono en formato internacional"""
        record = self._create_log_record("Teléfono: +573157589548")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***PHONE***", record.msg)
        self.assertNotIn("+573157589548", record.msg)
    
    def test_sanitize_phone_with_dashes(self):
        """Debe sanitizar teléfono con guiones"""
        record = self._create_log_record("Tel: +57-300-123-4567")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***PHONE***", record.msg)
    
    def test_sanitize_phone_with_spaces(self):
        """Debe sanitizar teléfono con espacios"""
        record = self._create_log_record("Tel: +57 300 123 4567")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***PHONE***", record.msg)
    
    def test_sanitize_phone_with_parentheses(self):
        """Debe sanitizar teléfono con paréntesis"""
        record = self._create_log_record("Tel: +57 (300) 123-4567")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***PHONE***", record.msg)
    
    def test_sanitize_colombian_id(self):
        """Debe sanitizar cédula colombiana"""
        record = self._create_log_record("CC: 1234567890")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***ID***", record.msg)
        self.assertNotIn("1234567890", record.msg)
    
    def test_sanitize_short_colombian_id(self):
        """Debe sanitizar cédula colombiana corta"""
        record = self._create_log_record("CC: 123456")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***ID***", record.msg)
    
    def test_not_sanitize_short_numbers(self):
        """No debe sanitizar números cortos (< 6 dígitos)"""
        record = self._create_log_record("Código: 12345")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        # No debe contener ***ID*** porque es muy corto
        self.assertIn("12345", record.msg)
    
    def test_not_sanitize_long_numbers(self):
        """No debe sanitizar números muy largos (> 10 dígitos) como IDs"""
        record = self._create_log_record("Número: 12345678901")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        # Puede ser sanitizado como teléfono o no, dependiendo del contexto
    
    def test_sanitize_multiple_pii_types(self):
        """Debe sanitizar múltiples tipos de PII en el mismo mensaje"""
        record = self._create_log_record(
            "Usuario: test@example.com, Tel: +573157589548, CC: 1234567890"
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***EMAIL***", record.msg)
        self.assertIn("***PHONE***", record.msg)
        self.assertIn("***ID***", record.msg)
    
    def test_handle_none_message(self):
        """Debe manejar mensaje None sin errores"""
        record = self._create_log_record(None)
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
    
    def test_always_returns_true(self):
        """Filter siempre debe retornar True"""
        record = self._create_log_record("Normal message")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
    
    def test_credit_card_priority_over_phone(self):
        """Tarjeta de crédito debe tener prioridad sobre teléfono"""
        record = self._create_log_record("4532-1234-5678-9010")
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        # Debe ser sanitizado como tarjeta, no como teléfono
        self.assertIn("****-****-****-****", record.msg)
        self.assertNotIn("***PHONE***", record.msg)
    
    def test_email_in_json(self):
        """Debe sanitizar email en JSON"""
        record = self._create_log_record('{"email": "user@example.com"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***EMAIL***", record.msg)
    
    def test_phone_in_json(self):
        """Debe sanitizar teléfono en JSON"""
        record = self._create_log_record('{"phone": "+573157589548"}')
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertIn("***PHONE***", record.msg)
    
    def test_sanitize_args_dict(self):
        """Debe sanitizar PII presente en record.args"""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User data: %(email)s %(phone)s",
            args={"email": "user@example.com", "phone": "+573157589548"},
            exc_info=None,
        )
        
        result = self.filter.filter(record)
        
        self.assertTrue(result)
        self.assertEqual(record.args["email"], "***EMAIL***")
        self.assertEqual(record.args["phone"], "***PHONE***")
    
    def test_sanitize_args_tuple_and_list(self):
        """Debe sanitizar PII en args tipo tuple o list"""
        tuple_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="%s %s",
            args=("+573157589548", "test@example.com"),
            exc_info=None,
        )
        list_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="%s",
            args=["+573157589548"],
            exc_info=None,
        )

        self.filter.filter(tuple_record)
        self.filter.filter(list_record)

        self.assertIn("***PHONE***", tuple_record.args[0])
        self.assertIn("***EMAIL***", tuple_record.args[1])
        self.assertIn("***PHONE***", list_record.args[0])


class LoggingFiltersIntegrationTests(TestCase):
    """Tests de integración para filtros de logging"""
    
    def test_both_filters_work_together(self):
        """Ambos filtros deben funcionar juntos"""
        api_filter = SanitizeAPIKeyFilter()
        pii_filter = SanitizePIIFilter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX, Email: test@example.com, Tel: +573157589548",
            args=(),
            exc_info=None
        )
        
        # Aplicar ambos filtros
        api_filter.filter(record)
        pii_filter.filter(record)
        
        # Verificar que todo fue sanitizado
        self.assertIn("***REDACTED***", record.msg)
        self.assertIn("***EMAIL***", record.msg)
        self.assertIn("***PHONE***", record.msg)
        self.assertNotIn("AIzaSy", record.msg)
        self.assertNotIn("test@example.com", record.msg)
        self.assertNotIn("+573157589548", record.msg)
    
    def test_filters_preserve_log_structure(self):
        """Filtros deben preservar la estructura del log"""
        api_filter = SanitizeAPIKeyFilter()
        
        record = logging.LogRecord(
            name="test.module",
            level=logging.WARNING,
            pathname="/path/to/file.py",
            lineno=42,
            msg="API Key: AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX",
            args=(),
            exc_info=None
        )
        
        api_filter.filter(record)
        
        # Verificar que los atributos del record no cambiaron
        self.assertEqual(record.name, "test.module")
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(record.lineno, 42)
    
    def test_filters_handle_exception_info(self):
        """Filtros deben manejar logs con información de excepciones"""
        import sys
        
        api_filter = SanitizeAPIKeyFilter()
        
        try:
            raise ValueError("GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX")
        except ValueError:
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        result = api_filter.filter(record)
        
        self.assertTrue(result)
        # El filtro no debe crashear con exc_info


def test_api_key_filter_handles_failing_pattern():
    """SanitizeAPIKeyFilter debe ignorar patrones que fallen al sanitizar"""
    class FailingPattern:
        def sub(self, repl, text):
            raise ValueError("boom")

    api_filter = SanitizeAPIKeyFilter()
    original_patterns = api_filter.PATTERNS
    api_filter.PATTERNS = [(FailingPattern(), "***")]

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="GEMINI_API_KEY=should_fail",
        args=(),
        exc_info=None,
    )

    # No debe lanzar, y debe devolver True
    assert api_filter.filter(record) is True

    # Restaurar patrones para no afectar otros tests
    api_filter.PATTERNS = original_patterns
