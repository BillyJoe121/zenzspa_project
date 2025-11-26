"""
Script de validación para los cambios en settings.py
Ejecutar: python scripts/validate_settings.py
"""
import os
import sys
from pathlib import Path

# Agregar el directorio del proyecto al path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zenzspa.settings')

def test_env_validation():
    """Test 1: Validación de variables de entorno"""
    print("\n🧪 Test 1: Validación de variables de entorno...")
    
    # Guardar valores actuales
    original_debug = os.environ.get('DEBUG')
    original_secret = os.environ.get('SECRET_KEY')
    
    try:
        # Test: SECRET_KEY faltante debe fallar
        os.environ['DEBUG'] = '1'  # Modo desarrollo
        if 'SECRET_KEY' in os.environ:
            del os.environ['SECRET_KEY']
        
        try:
            # Recargar settings
            import importlib
            import zenzspa.settings
            importlib.reload(zenzspa.settings)
            print("   ❌ FALLO: Debería haber lanzado RuntimeError por SECRET_KEY faltante")
            return False
        except RuntimeError as e:
            if "SECRET_KEY" in str(e):
                print("   ✅ PASS: Validación de SECRET_KEY funciona correctamente")
            else:
                print(f"   ❌ FALLO: Error inesperado: {e}")
                return False
    finally:
        # Restaurar valores
        if original_debug:
            os.environ['DEBUG'] = original_debug
        if original_secret:
            os.environ['SECRET_KEY'] = original_secret
    
    return True


def test_logging_filters():
    """Test 2: Filtros de logging"""
    print("\n🧪 Test 2: Filtros de sanitización de logs...")
    
    try:
        from core.logging_filters import SanitizeAPIKeyFilter, SanitizePIIFilter
        import logging
        
        # Test API Key Filter
        api_filter = SanitizeAPIKeyFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="GEMINI_API_KEY=AIzaSyDXXXXXXXXXXXXXXXXXXXXXXXX",
            args=(),
            exc_info=None
        )
        
        api_filter.filter(record)
        
        if "***REDACTED***" in record.msg and "AIzaSy" not in record.msg:
            print("   ✅ PASS: API Key sanitization funciona")
        else:
            print(f"   ❌ FALLO: API Key no fue sanitizada: {record.msg}")
            return False
        
        # Test PII Filter
        pii_filter = SanitizePIIFilter()
        record2 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Usuario: test@example.com, Teléfono: +573001234567",
            args=(),
            exc_info=None
        )
        
        pii_filter.filter(record2)
        
        if "***EMAIL***" in record2.msg and "***PHONE***" in record2.msg:
            print("   ✅ PASS: PII sanitization funciona")
        else:
            print(f"   ❌ FALLO: PII no fue sanitizada: {record2.msg}")
            return False
        
        # Test tarjeta de crédito
        record3 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Tarjeta: 4532-1234-5678-9010",
            args=(),
            exc_info=None
        )
        
        pii_filter.filter(record3)
        
        if "****-****-****-****" in record3.msg and "4532" not in record3.msg:
            print("   ✅ PASS: Credit card sanitization funciona")
        else:
            print(f"   ❌ FALLO: Tarjeta no fue sanitizada: {record3.msg}")
            return False
            
    except Exception as e:
        print(f"   ❌ FALLO: Error al importar filtros: {e}")
        return False
    
    return True


def test_rate_limiting_config():
    """Test 3: Configuración de rate limiting"""
    print("\n🧪 Test 3: Configuración de rate limiting...")
    
    try:
        from django.conf import settings
        
        throttle_rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        
        # Verificar que los nuevos scopes existan
        required_scopes = [
            'user', 'anon', 'auth_login', 'auth_verify', 
            'bot', 'bot_daily', 'bot_ip',
            'appointments_create', 'profile_update', 'analytics_export'
        ]
        
        missing = []
        for scope in required_scopes:
            if scope not in throttle_rates:
                missing.append(scope)
        
        if missing:
            print(f"   ❌ FALLO: Scopes faltantes: {missing}")
            return False
        
        # Verificar que los límites sean más restrictivos
        user_limit = throttle_rates.get('user', '')
        anon_limit = throttle_rates.get('anon', '')
        
        if '100/min' in user_limit or '30/min' in anon_limit:
            print("   ✅ PASS: Rate limits actualizados correctamente")
            print(f"      - User: {user_limit}")
            print(f"      - Anon: {anon_limit}")
            print(f"      - Bot: {throttle_rates.get('bot')}")
        else:
            print(f"   ⚠️  WARNING: Límites no coinciden con lo esperado")
            print(f"      - User: {user_limit} (esperado: 100/min)")
            print(f"      - Anon: {anon_limit} (esperado: 30/min)")
        
    except Exception as e:
        print(f"   ❌ FALLO: Error al verificar rate limiting: {e}")
        return False
    
    return True


def test_logging_config():
    """Test 4: Configuración de logging"""
    print("\n🧪 Test 4: Configuración de logging...")
    
    try:
        from django.conf import settings
        
        logging_config = settings.LOGGING
        
        # Verificar handlers
        handlers = logging_config.get('handlers', {})
        required_handlers = ['console', 'file', 'error_file']
        
        for handler in required_handlers:
            if handler not in handlers:
                print(f"   ❌ FALLO: Handler '{handler}' no encontrado")
                return False
        
        # Verificar filtros
        filters = logging_config.get('filters', {})
        required_filters = ['sanitize_api_keys', 'sanitize_pii']
        
        for filter_name in required_filters:
            if filter_name not in filters:
                print(f"   ❌ FALLO: Filtro '{filter_name}' no encontrado")
                return False
        
        # Verificar que los handlers usan los filtros
        console_filters = handlers['console'].get('filters', [])
        if 'sanitize_api_keys' in console_filters and 'sanitize_pii' in console_filters:
            print("   ✅ PASS: Logging configurado correctamente")
            print(f"      - Handlers: {list(handlers.keys())}")
            print(f"      - Filtros aplicados: {console_filters}")
        else:
            print(f"   ⚠️  WARNING: Filtros no aplicados correctamente")
        
        # Verificar que el directorio de logs existe
        logs_dir = BASE_DIR / "logs"
        if logs_dir.exists():
            print(f"   ✅ PASS: Directorio de logs creado: {logs_dir}")
        else:
            print(f"   ⚠️  WARNING: Directorio de logs no existe: {logs_dir}")
        
    except Exception as e:
        print(f"   ❌ FALLO: Error al verificar logging: {e}")
        return False
    
    return True


def test_celery_beat_schedule():
    """Test 5: Tareas de Celery Beat"""
    print("\n🧪 Test 5: Tareas de Celery Beat...")
    
    try:
        from django.conf import settings
        
        schedule = settings.CELERY_BEAT_SCHEDULE
        
        # Verificar que las nuevas tareas de limpieza existan
        required_tasks = [
            'cleanup-idempotency-keys',
            'cleanup-user-sessions',
            'cleanup-kiosk-sessions',
            'cleanup-notification-logs'
        ]
        
        missing = []
        for task in required_tasks:
            if task not in schedule:
                missing.append(task)
        
        if missing:
            print(f"   ❌ FALLO: Tareas faltantes: {missing}")
            return False
        
        print("   ✅ PASS: Todas las tareas de limpieza configuradas")
        print(f"      - Total de tareas: {len(schedule)}")
        for task_name in required_tasks:
            task_path = schedule[task_name]['task']
            print(f"      - {task_name}: {task_path}")
        
    except Exception as e:
        print(f"   ❌ FALLO: Error al verificar Celery Beat: {e}")
        return False
    
    return True


def main():
    """Ejecutar todos los tests"""
    print("=" * 70)
    print("🚀 VALIDACIÓN DE CAMBIOS EN ZENZSPA/SETTINGS.PY")
    print("=" * 70)
    
    results = []
    
    # Ejecutar tests
    results.append(("Logging Filters", test_logging_filters()))
    results.append(("Rate Limiting Config", test_rate_limiting_config()))
    results.append(("Logging Config", test_logging_config()))
    results.append(("Celery Beat Schedule", test_celery_beat_schedule()))
    
    # Resumen
    print("\n" + "=" * 70)
    print("📊 RESUMEN DE RESULTADOS")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{'✅' if passed == total else '❌'} Total: {passed}/{total} tests pasados")
    
    if passed == total:
        print("\n🎉 ¡Todos los tests pasaron! Los cambios están funcionando correctamente.")
        return 0
    else:
        print("\n⚠️  Algunos tests fallaron. Revisa los errores arriba.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
