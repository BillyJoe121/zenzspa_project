from django.http import JsonResponse
from django.db import connections
import logging

logger = logging.getLogger(__name__)


def health_check_view(request):
    """
    ZENZSPA-OPS-HEALTHCHECK: Health check robusto que verifica dependencias.
    
    Verifica:
    - Base de datos PostgreSQL
    - Redis (cache)
    - Celery workers (opcional, puede ser lento)
    
    Retorna 200 si todo está OK, 503 si alguna dependencia falla.
    """
    checks = {
        "db": False,
        "cache": False,
        "celery": False,
    }
    errors = []
    
    # 1. Verificar base de datos
    try:
        cursor = connections["default"].cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        checks["db"] = True
    except Exception as exc:
        errors.append(f"DB error: {str(exc)}")
        logger.error(f"Health check DB failed: {exc}")
    
    # 2. Verificar Redis
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
        redis_conn.ping()
        checks["cache"] = True
    except Exception as exc:
        errors.append(f"Cache error: {str(exc)}")
        logger.error(f"Health check Cache failed: {exc}")
    
    # 3. Verificar Celery (opcional, puede ser lento)
    # Solo verificar si se solicita explícitamente con ?check_celery=1
    if request.GET.get("check_celery") == "1":
        try:
            from celery.app.control import Inspect
            from zenzspa.celery import app as celery_app
            
            inspector = Inspect(app=celery_app)
            # Timeout de 2 segundos para no bloquear el health check
            active_workers = inspector.ping(timeout=2.0)
            checks["celery"] = bool(active_workers)
            if not active_workers:
                errors.append("No Celery workers responding")
        except Exception as exc:
            errors.append(f"Celery error: {str(exc)}")
            logger.error(f"Health check Celery failed: {exc}")
    else:
        # Si no se solicita, marcar como N/A
        checks["celery"] = "not_checked"
    
    # Determinar estado general
    critical_checks = [checks["db"], checks["cache"]]
    all_critical_ok = all(critical_checks)
    
    if all_critical_ok:
        return JsonResponse(
            {
                "status": "ok",
                "app": "zenzspa",
                "checks": checks,
            },
            status=200
        )
    else:
        return JsonResponse(
            {
                "status": "error",
                "app": "zenzspa",
                "checks": checks,
                "errors": errors,
            },
            status=503
        )
