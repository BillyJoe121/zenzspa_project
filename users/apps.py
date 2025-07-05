# Reemplaza todo el contenido de zenzspa_project/users/apps.py
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        """
        Importa las señales cuando la aplicación está lista.
        """
        import users.signals
