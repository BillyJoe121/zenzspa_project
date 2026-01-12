import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class BotTaskStatusView(APIView):
    """
    Endpoint para verificar el estado de una tarea de procesamiento de mensaje.

    Permite al frontend hacer polling para obtener la respuesta del bot
    cuando está siendo procesada en la cola.

    GET /api/v1/bot/task-status/<task_id>/
    """
    permission_classes = [AllowAny]  # Usuarios anónimos también pueden verificar

    def get(self, request, task_id):
        """
        Verifica el estado de una tarea de Celery.

        Returns:
            - status: 'pending' | 'processing' | 'success' | 'failure'
            - reply: Respuesta del bot (solo si success)
            - meta: Metadatos de la respuesta
            - progress: Posición en cola (opcional)
        """
        from celery.result import AsyncResult

        try:
            result = AsyncResult(task_id)

            if result.ready():
                # Tarea completada
                if result.successful():
                    task_result = result.result

                    if isinstance(task_result, dict) and 'error' not in task_result:
                        return Response({
                            'status': 'success',
                            'reply': task_result.get('reply'),
                            'meta': task_result.get('meta', {})
                        })
                    else:
                        return Response({
                            'status': 'failure',
                            'error': task_result.get('error', 'Error desconocido'),
                            'details': task_result.get('details')
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                else:
                    # Tarea falló
                    return Response({
                        'status': 'failure',
                        'error': 'Error procesando mensaje',
                        'details': str(result.info)
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                # Tarea aún procesando
                task_state = result.state

                response_data = {
                    'status': 'processing' if task_state == 'STARTED' else 'pending',
                    'message': 'Tu mensaje está siendo procesado. Por favor espera...'
                }

                # Si hay info adicional (ej: posición en cola)
                if result.info:
                    response_data['info'] = result.info

                return Response(response_data)

        except Exception as e:
            logger.exception("Error verificando estado de tarea %s: %s", task_id, e)
            return Response({
                'status': 'error',
                'error': 'No se pudo verificar el estado de la tarea'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

