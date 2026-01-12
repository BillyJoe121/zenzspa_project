#!/usr/bin/env python
"""
Script simple para verificar que las mejoras fueron implementadas correctamente.

Uso:
    python scripts/verify_improvements.py
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def main():
    print("\n" + "="*70)
    print("VERIFICACION DE MEJORAS IMPLEMENTADAS - STUDIOZENS".center(70))
    print("="*70 + "\n")
    
    # Verificar archivos modificados
    print("1. Archivos Modificados:")
    files_to_check = {
        "studiozens/settings/base.py": "Configuración principal",
        "studiozens/settings/security.py": "Seguridad y CSP",
        "studiozens/settings/celery.py": "Configuración de Celery",
        "studiozens/settings/logging.py": "Logging y monitoreo",
        "studiozens/health.py": "Health check mejorado",
    }
    
    for file_path, description in files_to_check.items():
        full_path = BASE_DIR / file_path
        if full_path.exists():
            print(f"  [OK] {file_path} - {description}")
        else:
            print(f"  [ERROR] {file_path} - NO ENCONTRADO")
    
    # Verificar archivos creados
    print("\n2. Documentación Creada:")
    docs_to_check = {
        "profiles/KIOSK_README.md": "Documentación de kiosko",
        "docs/security.md": "Guía de seguridad",
        "env.example.txt": "Ejemplo de variables de entorno",
        "MEJORAS_IMPLEMENTADAS.md": "Resumen de mejoras",
    }
    
    for doc_path, description in docs_to_check.items():
        full_path = BASE_DIR / doc_path
        if full_path.exists():
            print(f"  [OK] {doc_path} - {description}")
        else:
            print(f"  [WARN] {doc_path} - NO ENCONTRADO")
    
    # Verificar mejoras en settings.py
    print("\n3. Mejoras en settings:")
    settings_files = [
        BASE_DIR / "studiozens" / "settings" / "base.py",
        BASE_DIR / "studiozens" / "settings" / "security.py",
        BASE_DIR / "studiozens" / "settings" / "celery.py",
        BASE_DIR / "studiozens" / "settings" / "logging.py",
    ]

    existing_files = [path for path in settings_files if path.exists()]

    if existing_files:
        content = "\n".join(path.read_text() for path in existing_files)
        
        improvements = [
            "STUDIOZENS-SEC-ALLOWED-HOSTS",
            "STUDIOZENS-OPS-SITE-URL",
            "STUDIOZENS-SEC-PROXY-SSL",
            "STUDIOZENS-OPS-REDIS-TLS",
            "STUDIOZENS-OPS-CELERY-HARDENING",
            "STUDIOZENS-SEC-COOKIE-SAMESITE",
            "STUDIOZENS-CSP-CONNECT",
            "STUDIOZENS-API-VERSIONING",
            "STUDIOZENS-SENTRY-CELERY",
        ]
        
        implemented = 0
        for tag in improvements:
            if tag in content:
                print(f"  [OK] {tag}")
                implemented += 1
            else:
                print(f"  [WARN] {tag} - NO ENCONTRADO")
        
        print(f"\n  Implementadas: {implemented}/{len(improvements)}")
    else:
        print("  [ERROR] No se encontraron archivos de configuración en studiozens/settings/")
    
    # Verificar health check
    print("\n4. Health Check:")
    health_file = BASE_DIR / "studiozens" / "health.py"
    
    if health_file.exists():
        content = health_file.read_text()
        if "STUDIOZENS-OPS-HEALTHCHECK" in content:
            print("  [OK] Health check actualizado")
            if "connections" in content and "get_redis_connection" in content:
                print("  [OK] Verifica DB y Redis")
        else:
            print("  [WARN] Health check no actualizado")
    else:
        print("  [ERROR] health.py no encontrado")
    
    print("\n" + "="*70)
    print("VERIFICACION COMPLETADA".center(70))
    print("="*70 + "\n")
    
    print("Próximos pasos:")
    print("1. Revisar y actualizar tu archivo .env con las nuevas variables")
    print("2. Ejecutar: python -m scripts.validate_settings")
    print("3. Probar health check: curl http://localhost:8000/health/")
    print("4. Revisar MEJORAS_IMPLEMENTADAS.md para detalles completos\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
