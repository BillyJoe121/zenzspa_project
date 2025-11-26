"""
Script para ejecutar tests con reporte de cobertura
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def run_tests_with_coverage():
    """Ejecutar tests con pytest-cov"""
    print("=" * 70)
    print("🧪 EJECUTANDO TESTS CON COBERTURA")
    print("=" * 70)
    
    # Comando de pytest con cobertura
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "core/tests/test_logging_filters.py",
        "zenzspa/tests/test_settings.py",
        "-v",
        "--cov=core.logging_filters",
        "--cov=zenzspa.settings",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--tb=short",
        "--reuse-db"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=False)
        return result.returncode
    except FileNotFoundError:
        print("\n❌ ERROR: pytest no está instalado")
        print("Instala con: pip install pytest pytest-cov pytest-django")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return 1


def run_simple_tests():
    """Ejecutar solo tests de logging filters (sin Django)"""
    print("=" * 70)
    print("🧪 EJECUTANDO TESTS SIMPLES (sin Django)")
    print("=" * 70)
    
    cmd = [
        sys.executable,
        "scripts/test_logging_filters.py"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=BASE_DIR)
        return result.returncode
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return 1


def main():
    """Ejecutar tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ejecutar tests del proyecto")
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Ejecutar solo tests simples sin Django"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Ejecutar con reporte de cobertura"
    )
    
    args = parser.parse_args()
    
    if args.simple:
        return run_simple_tests()
    elif args.coverage:
        return run_tests_with_coverage()
    else:
        # Por defecto, ejecutar tests simples
        print("Ejecutando tests simples. Usa --coverage para tests completos.\n")
        return run_simple_tests()


if __name__ == "__main__":
    sys.exit(main())
