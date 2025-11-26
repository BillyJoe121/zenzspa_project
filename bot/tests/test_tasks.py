import time
from types import SimpleNamespace
import uuid

import pytest
from celery.exceptions import Retry
from django.core.cache import cache
from django.utils import timezone
from model_bakery import baker

# Importamos las tareas (asegúrate que Celery no se ejecute real, solo la función)
from bot.tasks import (
    report_daily_token_usage,
    cleanup_old_bot_logs,
    monitor_bot_health,
    process_bot_message_async,
    cleanup_expired_anonymous_users,
    _check_rate_limit,
    GEMINI_RATE_LIMIT_KEY,
    GEMINI_MAX_REQUESTS_PER_MINUTE,
)
from bot.models import BotConversationLog, BotConfiguration, AnonymousUser

@pytest.mark.django_db
class TestBotTasks:
    
    def test_report_daily_token_usage(self, bot_config):
        """Debe calcular costos correctamente."""
        # Configurar precios en la config existente
        bot_config.api_input_price_per_1k = 0.001
        bot_config.api_output_price_per_1k = 0.002
        bot_config.save()

        # Crear logs de ayer con la fecha correcta
        from datetime import date, datetime
        yesterday_date = (timezone.now().date() - timezone.timedelta(days=1))
        yesterday_datetime = datetime.combine(yesterday_date, datetime.min.time())
        yesterday_datetime = timezone.make_aware(yesterday_datetime)

        # Log 1: 1000 input tokens, 500 output tokens (Total 1500)
        log = BotConversationLog.objects.create(
            message="Test message",
            response="Test response",
            tokens_used=1500,
            response_meta={'prompt_tokens': 1000, 'completion_tokens': 500},
            ip_address="127.0.0.1",
            was_blocked=False
        )
        # Forzar created_at (auto_now_add impide setearlo en create)
        log.created_at = yesterday_datetime
        log.save()

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

    def test_check_rate_limit_blocks_when_full(self):
        """_check_rate_limit debe indicar espera si alcanzamos 15 RPM."""
        now = time.time()
        cache.set(
            GEMINI_RATE_LIMIT_KEY,
            [now - 1 for _ in range(GEMINI_MAX_REQUESTS_PER_MINUTE)],
            70,
        )

        can_proceed, wait_seconds = _check_rate_limit()

        assert can_proceed is False
        assert wait_seconds > 0

    def test_check_rate_limit_allows_when_empty(self):
        """_check_rate_limit debe permitir la primera llamada."""
        can_proceed, wait_seconds = _check_rate_limit()

        assert can_proceed is True
        assert wait_seconds == 0

    def test_process_bot_message_async_rate_limited(self, mocker):
        """Cuando hay rate limit, la tarea debe reintentar."""
        mocker.patch("bot.tasks._check_rate_limit", return_value=(False, 2))

        # Mockear retry para que lance la excepción Retry
        mock_retry = mocker.Mock(side_effect=Retry())
        
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-1", retries=0),
            max_retries=5,
            retry=mock_retry,
        )

        with pytest.raises(Retry):
            try:
                process_bot_message_async.run(message="hola")
            except TypeError:
                process_bot_message_async.run(self=task, message="hola")

    def test_process_bot_message_async_creates_log(self, mocker):
        """Flujo feliz crea el log y retorna la respuesta."""
        mocker.patch("bot.tasks._check_rate_limit", return_value=(True, 0))
        mocker.patch(
            "bot.services.PromptOrchestrator.build_full_prompt",
            return_value=("prompt", True),
        )
        mocker.patch(
            "bot.services.GeminiService.generate_response",
            return_value=({"reply_to_user": "hi", "analysis": {"action": "REPLY"}}, {"tokens": 5, "source": "gemini"}),
        )

        user = baker.make("users.CustomUser")
        mock_retry = mocker.Mock(side_effect=Retry())
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-2", retries=0),
            max_retries=5,
            retry=mock_retry,
        )

        try:
            result = process_bot_message_async.run(
                user.id, # user_id
                None,    # anonymous_user_id
                "hola",  # message
                "1.1.1.1", # client_ip
                ["prev"], # history
            )
        except TypeError:
            result = process_bot_message_async.run(
                self=task,
                user_id=user.id,
                anonymous_user_id=None,
                message="hola",
                client_ip="1.1.1.1",
                conversation_history=["prev"]
            )

        assert result["reply"] == "hi"
        log = BotConversationLog.objects.get(id=result["meta"]["log_id"])
        assert log.user == user
        assert log.ip_address == "1.1.1.1"

    def test_process_bot_message_async_missing_user(self, mocker):
        """Si el usuario no existe, debe regresar error sin llamar a Gemini."""
        mocker.patch("bot.tasks._check_rate_limit", return_value=(True, 0))
        mocker.patch(
            "bot.services.PromptOrchestrator.build_full_prompt",
            return_value=("prompt", True),
        )
        mock_gemini = mocker.patch("bot.services.GeminiService.generate_response")

        mock_retry = mocker.Mock(side_effect=Retry())
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-3", retries=0),
            max_retries=5,
            retry=mock_retry,
        )

        fake_uuid = uuid.uuid4()
        
        try:
            result = process_bot_message_async.run(
                fake_uuid, 
                None, 
                "hola"
            )
        except TypeError:
             result = process_bot_message_async.run(
                self=task,
                user_id=fake_uuid,
                anonymous_user_id=None,
                message="hola"
            )

        assert result["error"] == "Usuario no encontrado"
        mock_gemini.assert_not_called()

    def test_process_bot_message_async_returns_error_after_retries(self, mocker):
        """Si ya no hay reintentos, devuelve error sin lanzar Retry."""
        mocker.patch("bot.tasks._check_rate_limit", return_value=(True, 0))
        mocker.patch(
            "bot.services.PromptOrchestrator.build_full_prompt",
            return_value=("prompt", True),
        )
        mocker.patch(
            "bot.services.GeminiService.generate_response",
            side_effect=ValueError("boom"),
        )

        mock_retry = mocker.Mock(side_effect=Retry())
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-4", retries=5),
            max_retries=5,
            retry=mock_retry,
        )

        try:
            result = process_bot_message_async.run(
                None, # user_id
                None, # anon_id
                "hola", # message
                "1.1.1.1" # client_ip
            )
        except TypeError:
            result = process_bot_message_async.run(
                self=task,
                user_id=None,
                anonymous_user_id=None,
                message="hola",
                client_ip="1.1.1.1"
            )

        assert result["error"] == "Error procesando mensaje"
        assert "boom" in result["details"]

    def test_report_daily_token_usage_without_config(self):
        """Sin configuración activa, devuelve error."""
        BotConfiguration.objects.all().delete()

        report = report_daily_token_usage()

        assert report == {"error": "No active bot configuration"}

    def test_report_daily_token_usage_estimates_tokens(self, bot_config):
        """Cuando no hay desglose prompt/completion, usa proporción 60/40 y dispara alertas."""
        bot_config.api_input_price_per_1k = 1
        bot_config.api_output_price_per_1k = 1
        bot_config.daily_cost_alert_threshold = 0.05
        bot_config.avg_tokens_alert_threshold = 10
        bot_config.save()

        # Crear logs de ayer con la fecha correcta
        from datetime import date, datetime
        yesterday_date = (timezone.now().date() - timezone.timedelta(days=1))
        yesterday_datetime = datetime.combine(yesterday_date, datetime.min.time())
        yesterday_datetime = timezone.make_aware(yesterday_datetime)

        # Crear log manualmente y actualizar fecha
        log = BotConversationLog.objects.create(
            message="Test message",
            response="Test response",
            tokens_used=100,
            was_blocked=False,  # Cambiado a False para que sea contado
            response_meta={},
            ip_address="127.0.0.1"
        )
        # Forzar created_at (auto_now_add impide setearlo en create)
        log.created_at = yesterday_datetime
        log.save()

        report = report_daily_token_usage()

        assert report["input_tokens"] == 60
        assert report["output_tokens"] == 40
        assert report["estimated_cost_usd"] > bot_config.daily_cost_alert_threshold

    def test_cleanup_expired_anonymous_users(self):
        """Solo elimina usuarios anónimos expirados y no convertidos."""
        now = timezone.now()
        expired = baker.make(
            AnonymousUser,
            expires_at=now - timezone.timedelta(days=1),
            converted_to_user=None,
        )
        active = baker.make(
            AnonymousUser,
            expires_at=now + timezone.timedelta(days=1),
            converted_to_user=None,
        )

        result = cleanup_expired_anonymous_users()

        assert result["deleted_count"] == 1
        assert not AnonymousUser.objects.filter(id=expired.id).exists()
        assert AnonymousUser.objects.filter(id=active.id).exists()
