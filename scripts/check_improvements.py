#!/usr/bin/env python
"""
Script de migración para verificar la configuración después de implementar las mejoras.

Uso:
    python scripts/check_improvements.py

Este script verifica:
1. Que todas las nuevas variables de entorno estén documentadas
2. Que las validaciones funcionen correctamente
3. Que no haya configuraciones inseguras
"""

import os
import sys
from pathlib import Path

# Agregar el directorio raíz al path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def print_header(text):
    print(f"\n{'='*70}")
    print(f"{text.center(70)}")
    print(f"{'='*70}\n")


def print_success(text):
    print(f"[OK] {text}")


def print_warning(text):
    print(f"[WARN] {text}")


def print_error(text):
    print(f"[ERROR] {text}")


def print_info(text):
    print(f"[INFO] {text}")



def check_env_file():
    """Verificar que existe un archivo .env"""
    print_header("1. Verificación de Archivo .env")
    
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        print_success(f"Archivo .env encontrado: {env_file}")
        return True
    else:
        print_error("Archivo .env no encontrado")
        print_info("Copia env.example.txt a .env y configura las variables")
        return False


def check_new_variables():
    """Verificar nuevas variables de entorno"""
    print_header("2. Verificación de Nuevas Variables")
    
    new_vars = {
        # Críticas
        "TRUST_PROXY": "Configuración de proxy (0 o 1)",
        "SESSION_COOKIE_SAMESITE": "Política SameSite para cookies de sesión",
        
        # Importantes
        "CSP_REPORT_URI": "URI para reportes CSP (opcional)",
        "NEW_RELIC_CONFIG_FILE": "Ruta al archivo de configuración New Relic (opcional)",
        "DEBUG_TOOLBAR_IPS": "IPs permitidas para debug toolbar (opcional)",
        "GIT_COMMIT": "Commit de Git para Sentry release tracking (opcional)",
        
        # Celery
        "CELERY_TASK_TIME_LIMIT": "Límite de tiempo por tarea Celery (opcional)",
        "CELERY_TASK_SOFT_TIME_LIMIT": "Límite suave de tiempo (opcional)",
        "CELERY_WORKER_MAX_TASKS_PER_CHILD": "Máximo de tareas por worker (opcional)",
    }
    
    missing_optional = []
    configured = []
    
    for var, description in new_vars.items():
        value = os.getenv(var)
        if value:
            configured.append(var)
        
        checks = {
            "ALLOWED_HOSTS": "Debe estar configurado sin localhost",
            "CORS_ALLOWED_ORIGINS": "Debe estar configurado con HTTPS",
            "REDIS_URL": "Debe usar rediss:// (TLS)",
            "CELERY_BROKER_URL": "Debe usar rediss:// (TLS)",
            "SITE_URL": "Debe usar https://",
            "WOMPI_REDIRECT_URL": "Debe usar https://",
            "SENTRY_DSN": "Recomendado para monitoreo",
        }
        
        all_ok = True
        for var, requirement in checks.items():
            value = os.getenv(var, "")
            
            if var in ["ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS"]:
                if "localhost" in value or "127.0.0.1" in value:
                    print_error(f"{var}: Contiene localhost - {requirement}")
                    all_ok = False
                elif value:
                    print_success(f"{var}: Configurado correctamente")
                else:
                    print_error(f"{var}: No configurado - {requirement}")
                    all_ok = False
            
            elif var in ["REDIS_URL", "CELERY_BROKER_URL"]:
                if value.startswith("rediss://"):
                    print_success(f"{var}: Usa TLS (rediss://)")
                elif value.startswith("redis://"):
                    print_error(f"{var}: No usa TLS - {requirement}")
                    all_ok = False
                else:
                    print_error(f"{var}: No configurado - {requirement}")
                    all_ok = False
            
            elif var in ["SITE_URL", "WOMPI_REDIRECT_URL"]:
                if value.startswith("https://"):
                    print_success(f"{var}: Usa HTTPS")
                elif value.startswith("http://"):
                    print_error(f"{var}: No usa HTTPS - {requirement}")
                    all_ok = False
                else:
                    print_error(f"{var}: No configurado - {requirement}")
                    all_ok = False
            
            elif var == "SENTRY_DSN":
                if value:
                    print_success(f"{var}: Configurado")
                else:
                    print_warning(f"{var}: No configurado - {requirement}")
        
        return all_ok
    else:
        print_info("Modo DEBUG activado - Saltando verificación de producción")
        return True


def check_health_endpoint():
    """Verificar que el health endpoint esté actualizado"""
    print_header("4. Verificación de Health Check")
    
    health_file = BASE_DIR / "zenzspa" / "health.py"
    
    if health_file.exists():
        content = health_file.read_text()
        
        if "ZENZSPA-OPS-HEALTHCHECK" in content:
            print_success("Health check actualizado con verificación de dependencias")
            
            if "connections[\"default\"]" in content:
                print_success("  ✓ Verifica base de datos")
            
            if "get_redis_connection" in content:
                print_success("  ✓ Verifica Redis")
            
            if "Inspect" in content:
                print_success("  ✓ Verifica Celery (opcional)")
            
            return True
        else:
            print_warning("Health check no actualizado - considera actualizar zenzspa/health.py")
            return False
    else:
        print_error("Archivo health.py no encontrado")
        return False


def check_documentation():
    """Verificar que la documentación esté creada"""
    print_header("5. Verificación de Documentación")
    
    docs = {
        "profiles/KIOSK_README.md": "Documentación del sistema de kiosko",
        "docs/security.md": "Guía de seguridad",
        "env.example.txt": "Ejemplo de variables de entorno",
        "MEJORAS_IMPLEMENTADAS.md": "Resumen de mejoras implementadas",
    }
    
    all_exist = True
    for doc_path, description in docs.items():
        doc_file = BASE_DIR / doc_path
        if doc_file.exists():
            print_success(f"{doc_path}: {description}")
        else:
            print_warning(f"{doc_path}: {description} - NO ENCONTRADO")
            all_exist = False
    
    return all_exist


def check_settings_improvements():
    """Verificar mejoras en settings.py"""
    print_header("6. Verificación de Mejoras en settings.py")
    
    settings_file = BASE_DIR / "zenzspa" / "settings.py"
    
    if not settings_file.exists():
        print_error("Archivo settings.py no encontrado")
        return False
    
    content = settings_file.read_text()
    
    improvements = {
        "ZENZSPA-SEC-ALLOWED-HOSTS": "Validación de ALLOWED_HOSTS",
        "ZENZSPA-OPS-SITE-URL": "Validación de SITE_URL",
        "ZENZSPA-SEC-PROXY-SSL": "Configuración de proxy SSL",
        "ZENZSPA-OPS-REDIS-TLS": "Validación de Redis TLS",
        "ZENZSPA-OPS-CELERY-HARDENING": "Hardening de Celery",
        "ZENZSPA-SEC-COOKIE-SAMESITE": "Configuración de cookies SameSite",
        "ZENZSPA-CSP-CONNECT": "CSP mejorado",
        "ZENZSPA-API-VERSIONING": "Versionado de API",
        "ZENZSPA-SENTRY-CELERY": "Integración Sentry-Celery",
        "ZENZSPA-REDIS-WATCHDOG": "Redis watchdog",
        "ZENZSPA-WOMPI-REDIRECT": "Validación Wompi redirect",
        "ZENZSPA-CELERYBEAT-ARTIFACTS": "Celery Beat artifacts",
        "ZENZSPA-NEWRELIC-CONFIG": "Configuración New Relic",
        "ZENZSPA-DEBUG-TOOLBAR": "Debug toolbar mejorado",
    }
    
    implemented = 0
    for tag, description in improvements.items():
        if tag in content:
            print_success(f"{tag}: {description}")
            implemented += 1
        else:
            print_warning(f"{tag}: {description} - NO ENCONTRADO")
    
    print(f"\n{Colors.BOLD}Resumen:{Colors.ENDC}")
    print(f"  Implementadas: {implemented}/{len(improvements)}")
    
    return implemented == len(improvements)


def main():
    """Función principal"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║                                                                    ║")
    print("║          VERIFICACIÓN DE MEJORAS IMPLEMENTADAS - ZENZSPA          ║")
    print("║                                                                    ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")
    
    results = {
        "Archivo .env": check_env_file(),
        "Nuevas variables": check_new_variables(),
        "Requisitos de producción": check_production_requirements(),
        "Health check": check_health_endpoint(),
        "Documentación": check_documentation(),
        "Mejoras en settings.py": check_settings_improvements(),
    }
    
    # Resumen final
    print_header("RESUMEN FINAL")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for check, result in results.items():
        if result:
            print_success(f"{check}: OK")
        else:
            print_warning(f"{check}: REVISAR")
    
    print(f"\n{Colors.BOLD}Resultado: {passed}/{total} verificaciones pasadas{Colors.ENDC}\n")
    
    if passed == total:
        print_success("¡Todas las verificaciones pasaron correctamente!")
        print_info("El proyecto está listo para usar las nuevas mejoras.")
        return 0
    else:
        print_warning("Algunas verificaciones necesitan atención.")
        print_info("Revisa los mensajes anteriores para más detalles.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
