import os

from celery.schedules import crontab

from .base import BASE_DIR, DEBUG, TIME_ZONE

# --------------------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")

# STUDIOZENS-OPS-REDIS-TLS: Validar Celery broker TLS en producción
if not DEBUG:
    if not CELERY_BROKER_URL.startswith("rediss://"):
        raise RuntimeError(
            "CELERY_BROKER_URL debe usar rediss:// (TLS) en producción. "
            f"URL actual: {CELERY_BROKER_URL.split('@')[-1] if '@' in CELERY_BROKER_URL else CELERY_BROKER_URL}"
        )

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# STUDIOZENS-CELERYBEAT-ARTIFACTS: Mover schedule fuera del repo
CELERY_BEAT_SCHEDULE_FILENAME = os.getenv(
    "CELERY_BEAT_SCHEDULE_FILENAME",
    "/var/run/studiozens/celerybeat-schedule" if not DEBUG else str(BASE_DIR / "celerybeat-schedule"),
)

# STUDIOZENS-OPS-CELERY-HARDENING: Configuración robusta de Celery
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "120"))  # 2 minutos
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "100"))  # 100 segundos
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "500"))

# Rutas de tareas a colas dedicadas
CELERY_TASK_ROUTES = {
    "finances.tasks.run_developer_payout": {"queue": "payments"},
    "finances.tasks.*": {"queue": "payments"},
    "spa.tasks.*": {"queue": "appointments"},
    "notifications.tasks.*": {"queue": "notifications"},
    "bot.tasks.*": {"queue": "bot"},
}

CELERY_BEAT_SCHEDULE = {
    "check-for-reminders-every-hour": {
        "task": "spa.tasks.send_appointment_reminder",
        "schedule": crontab(minute="0", hour="*"),
    },
    "cancel-unpaid-appointments-every-10-minutes": {
        "task": "spa.tasks.cancel_unpaid_appointments",
        "schedule": crontab(minute="*/10"),
    },
    "release-expired-order-reservations": {
        "task": "marketplace.tasks.release_expired_order_reservations",
        "schedule": crontab(minute="*/10"),
    },
    # Tareas de pagos y finanzas
    "developer-payout-hourly": {
        "task": "finances.tasks.run_developer_payout",
        "schedule": crontab(minute=0, hour="*"),
    },
    "check-pending-payments-every-15-minutes": {
        "task": "finances.tasks.check_pending_payments",
        "schedule": crontab(minute="*/15"),
    },
    "process-recurring-vip-subscriptions-daily": {
        "task": "finances.tasks.process_recurring_subscriptions",
        "schedule": crontab(minute=0, hour=2),
    },
    "downgrade-expired-vips-daily": {
        "task": "finances.tasks.downgrade_expired_vips",
        "schedule": crontab(minute=30, hour=2),
    },
    # Tareas del bot
    "bot-daily-token-report": {
        "task": "bot.tasks.report_daily_token_usage",
        "schedule": crontab(minute=0, hour=8),
    },
    "bot-cleanup-old-logs": {
        "task": "bot.tasks.cleanup_old_bot_logs",
        "schedule": crontab(minute=0, hour=3, day_of_week=0),
    },
    # Tareas de limpieza y mantenimiento
    "cleanup-idempotency-keys": {
        "task": "core.tasks.cleanup_old_idempotency_keys",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-user-sessions": {
        "task": "users.tasks.cleanup_inactive_sessions",
        "schedule": crontab(hour=4, minute=0),
    },
    "cleanup-kiosk-sessions": {
        "task": "profiles.tasks.cleanup_expired_kiosk_sessions",
        "schedule": crontab(hour=3, minute=30),
    },
    "cleanup-notification-logs": {
        "task": "notifications.tasks.cleanup_old_notification_logs",
        "schedule": crontab(hour=2, minute=0),
    },
    # Tareas huérfanas activadas
    "check-upcoming-appointments-2h": {
        "task": "notifications.tasks.check_upcoming_appointments_2h",
        "schedule": crontab(minute="*/5"),  # Revisar cada 5 min
    },
    "notify-expiring-vouchers-daily": {
        "task": "spa.tasks.notify_expiring_vouchers",
        "schedule": crontab(hour=9, minute=0),  # 9:00 AM
    },
    "check-vip-loyalty-rewards": {
        "task": "spa.tasks.check_vip_loyalty",
        "schedule": crontab(hour=6, minute=0),  # 6:00 AM
    },
    "monitor-bot-health": {
        "task": "bot.tasks.monitor_bot_health",
        "schedule": crontab(minute="*/5"),  # Cada 5 min
    },
    "cleanup-expired-carts-hourly": {
        "task": "marketplace.tasks.cleanup_expired_carts",
        "schedule": crontab(minute=0, hour="*"),
    },
    "cleanup-webhook-events": {
        "task": "finances.tasks.cleanup_old_webhook_events",
        "schedule": crontab(hour=3, minute=15, day_of_week=0),  # Domingos a las 3:15 AM
    },
}
