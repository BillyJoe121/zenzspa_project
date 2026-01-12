"""
Vista de health check para verificar el estado del servicio del bot.
"""
import logging

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ...models import BotConfiguration

logger = logging.getLogger(__name__)


class BotHealthCheckView(APIView):
    """
    BOT-HEALTH-PARTIAL: Health check mejorado que verifica dependencias reales.

    Verifica:
    - Cache (Redis)
    - Base de datos
    - Gemini API configuration
    - Configuración activa del bot
    - Celery workers (opcional con ?check_celery=1)

    Retorna 200 si todo está OK, 503 si alguna dependencia crítica falla.
    """
    permission_classes = []  # Público para load balancers

    def get(self, request):
        # Verificar si se solicita detalle (solo para staff)
        show_details = request.query_params.get('details') == '1' and (
            request.user.is_authenticated and request.user.is_staff
        )

        checks = {
            'cache': self._check_cache(),
            'database': self._check_database(),
            'gemini_api': self._check_gemini(),
            'configuration': self._check_config(),
        }

        # Verificar Celery solo si se solicita explícitamente
        if request.query_params.get('check_celery') == '1':
            checks['celery'] = self._check_celery()

        # Determinar salud general (cache, db y config son críticos)
        critical_checks = [checks['cache'], checks['database'], checks['configuration']]
        all_healthy = all(critical_checks)

        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        # Respuesta básica para load balancers
        response_data = {
            'status': 'healthy' if all_healthy else 'unhealthy',
            'service': 'bot',
        }

        # Si se solicitan detalles y el usuario es staff, incluir componentes
        if show_details:
            response_data['components'] = checks

        return Response(response_data, status=status_code)

    def _check_cache(self) -> bool:
        """Verifica que Redis/cache esté funcionando"""
        try:
            test_key = 'bot_health_check_test'
            cache.set(test_key, 'ok', 10)
            result = cache.get(test_key)
            cache.delete(test_key)
            return result == 'ok'
        except Exception as e:
            logger.error("Health check cache failed: %s", e)
            return False

    def _check_database(self) -> bool:
        """Verifica que la base de datos esté funcionando"""
        try:
            from django.db import connections
            cursor = connections['default'].cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Exception as e:
            logger.error("Health check database failed: %s", e)
            return False

    def _check_gemini(self) -> bool:
        """
        Verifica que la API key de Gemini esté configurada Y que el SDK esté instalado.
        """
        try:
            import os
            from django.conf import settings

            # 1. Verificar API Key
            api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                return False

            # 2. Verificar instalación del SDK
            try:
                from google import genai
                # 3. Verificar instanciación básica (sin llamada de red)
                client = genai.Client(api_key=api_key)
                return True
            except ImportError:
                logger.error("Health check Gemini failed: google-genai not installed")
                return False
            except Exception as e:
                logger.error("Health check Gemini failed during init: %s", e)
                return False

        except Exception as e:
            logger.error("Health check Gemini failed: %s", e)
            return False

    def _check_config(self) -> bool:
        """Verifica que exista una configuración activa"""
        try:
            config = BotConfiguration.objects.filter(is_active=True).first()
            return config is not None
        except Exception as e:
            logger.error("Health check config failed: %s", e)
            return False

    def _check_celery(self) -> bool:
        """
        Verifica que haya workers de Celery activos.
        Solo se ejecuta si se solicita explícitamente.
        """
        try:
            from celery.app.control import Inspect
            from studiozens.celery import app as celery_app

            inspector = Inspect(app=celery_app)
            # Timeout de 2 segundos para no bloquear el health check
            active_workers = inspector.ping(timeout=2.0)
            return bool(active_workers)
        except Exception as e:
            logger.error("Health check Celery failed: %s", e)
            return False
