"""
Test simple de los filtros de logging (sin Django)
"""
import sys
from pathlib import Path

# Agregar el directorio del proyecto al path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

def test_logging_filters():
    """Test de filtros de logging"""
    print("🧪 Probando filtros de logging...")
    
    try:
        from core.logging_filters import SanitizeAPIKeyFilter, SanitizePIIFilter
        import logging
        
        # Test 1: API Key Filter
        print("\n1️⃣ Test: Sanitización de API Keys")
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
            print("   ✅ PASS: API Key fue sanitizada correctamente")
            print(f"   Mensaje: {record.msg}")
        else:
            print(f"   ❌ FAIL: API Key NO fue sanitizada")
            print(f"   Mensaje: {record.msg}")
            return False
        
        # Test 2: PII Filter - Email y Teléfono
        print("\n2️⃣ Test: Sanitización de PII (Email y Teléfono)")
        pii_filter = SanitizePIIFilter()
        record2 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Usuario: test@example.com, Teléfono: +573157589548",
            args=(),
            exc_info=None
        )
        
        pii_filter.filter(record2)
        
        if "***EMAIL***" in record2.msg and "***PHONE***" in record2.msg:
            print("   ✅ PASS: Email y teléfono sanitizados")
            print(f"   Mensaje: {record2.msg}")
        else:
            print(f"   ❌ FAIL: PII NO fue sanitizada")
            print(f"   Mensaje: {record2.msg}")
            return False
        
        # Test 3: Tarjeta de crédito
        print("\n3️⃣ Test: Sanitización de Tarjetas de Crédito")
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
            print("   ✅ PASS: Tarjeta sanitizada")
            print(f"   Mensaje: {record3.msg}")
        else:
            print(f"   ❌ FAIL: Tarjeta NO fue sanitizada")
            print(f"   Mensaje: {record3.msg}")
            return False
        
        # Test 4: Robustez - manejo de excepciones
        print("\n4️⃣ Test: Robustez (manejo de excepciones)")
        record4 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=None,  # Mensaje None para probar robustez
            args=(),
            exc_info=None
        )
        
        try:
            api_filter.filter(record4)
            pii_filter.filter(record4)
            print("   ✅ PASS: Filtros manejan valores None sin errores")
        except Exception as e:
            print(f"   ❌ FAIL: Filtros lanzaron excepción: {e}")
            return False
        
        print("\n" + "="*60)
        print("✅ TODOS LOS TESTS DE LOGGING FILTERS PASARON")
        print("="*60)
        return True
        
    except ImportError as e:
        print(f"❌ ERROR: No se pudo importar los filtros: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_logging_filters()
    sys.exit(0 if success else 1)
