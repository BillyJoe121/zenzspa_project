import pytest
from django.utils import timezone
from model_bakery import baker
# Importamos las tareas (asegúrate que Celery no se ejecute real, solo la función)
from bot.tasks import report_daily_token_usage, cleanup_old_bot_logs, monitor_bot_health
from bot.models import BotConversationLog, BotConfiguration

@pytest.mark.django_db
class TestBotTasks:
    
    def test_report_daily_token_usage(self, bot_config):
        """Debe calcular costos correctamente."""
        # Configurar precios en la config existente
        bot_config.api_input_price_per_1k = 0.001
        bot_config.api_output_price_per_1k = 0.002
        bot_config.save()
        
        # Crear logs de ayer
        yesterday = timezone.now() - timezone.timedelta(days=1)
        # Log 1: 1000 input tokens, 500 output tokens (Total 1500)
        baker.make(BotConversationLog, 
            created_at=yesterday,
            tokens_used=1500,
            response_meta={'prompt_tokens': 1000, 'completion_tokens': 500}
        )
        
        # Ejecutamos la tarea sincrónicamente
        report = report_daily_token_usage()
        
        assert report['total_conversations'] == 1
        assert report['total_tokens'] == 1500
        # Costo esperado: (1 * 0.001) + (0.5 * 0.002) = 0.001 + 0.001 = 0.002
        assert report['estimated_cost_usd'] == 0.002

    def test_cleanup_old_logs(self):
        """Debe borrar logs más antiguos que X días."""
        old_date = timezone.now() - timezone.timedelta(days=100)
        recent_date = timezone.now() - timezone.timedelta(days=10)
        
        # Crear log antiguo (debe morir)
        log1 = baker.make(BotConversationLog)
        log1.created_at = old_date
        log1.save()
        
        # Crear log reciente (debe vivir)
        log2 = baker.make(BotConversationLog)
        log2.created_at = recent_date
        log2.save()
        
        # Ejecutar limpieza (default 90 días)
        res = cleanup_old_bot_logs(days_to_keep=90)

        assert res['deleted_count'] == 1
        assert BotConversationLog.objects.count() == 1 # Solo queda el reciente

    def test_monitor_bot_health_no_activity(self):
        """Sin actividad reciente, debe retornar no_activity"""
        result = monitor_bot_health()
        assert result['status'] == 'no_activity'

    def test_monitor_bot_health_normal(self):
        """Con actividad normal, no debe generar alertas"""
        # Crear logs recientes normales
        now = timezone.now()
        for _ in range(10):
            baker.make(BotConversationLog,
                created_at=now - timezone.timedelta(minutes=2),
                was_blocked=False,
                latency_ms=1000  # 1 segundo - normal
            )

        result = monitor_bot_health()

        assert result['total_requests'] == 10
        assert result['blocked'] == 0
        assert result['block_rate'] == 0
        assert result['avg_latency_ms'] == 1000
        assert result['alerts'] == []

    def test_monitor_bot_health_high_block_rate(self):
        """Con tasa de bloqueo alta (>20%), debe generar alerta"""
        now = timezone.now()

        # 8 bloqueados, 2 normales = 80% block rate
        for _ in range(8):
            baker.make(BotConversationLog,
                created_at=now - timezone.timedelta(minutes=2),
                was_blocked=True,
                latency_ms=500
            )
        for _ in range(2):
            baker.make(BotConversationLog,
                created_at=now - timezone.timedelta(minutes=2),
                was_blocked=False,
                latency_ms=500
            )

        result = monitor_bot_health()

        assert result['total_requests'] == 10
        assert result['blocked'] == 8
        assert result['block_rate'] == 80.0
        assert len(result['alerts']) == 1
        assert 'block_rate_high' in result['alerts'][0]

    def test_monitor_bot_health_high_latency(self):
        """Con latencia alta (>5000ms), debe generar alerta"""
        now = timezone.now()

        for _ in range(5):
            baker.make(BotConversationLog,
                created_at=now - timezone.timedelta(minutes=2),
                was_blocked=False,
                latency_ms=6000  # 6 segundos - alto
            )

        result = monitor_bot_health()

        assert result['total_requests'] == 5
        assert result['avg_latency_ms'] == 6000
        assert len(result['alerts']) == 1
        assert 'latency_high' in result['alerts'][0]