from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"

    def ready(self):
        # Ensures that tasks and signal handlers are registered
        import notifications.tasks  # noqa: F401
